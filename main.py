import flet as ft
import pandas as pd
import random
import threading
import time
import asyncio

# --- CONFIGURATION & COLORS ---
THEME_COLORS = {
    "light": {
        "bg_main": "#F3F4F6",
        "card_bg": "#ffffff",
        "text": "#1F2937",
        "accent": "#3B82F6",
        "success": "#059669",
        "error": "#DC2626",
        "warning": "#D97706",
        "neutral": "#E5E7EB",
        "text_btn": "#374151",
        "text_dim": "#9CA3AF",
    },
    "dark": {
        "bg_main": "#1a1a1a",
        "card_bg": "#2b2b2b",
        "text": "#E5E7EB",
        "accent": "#3B82F6",
        "success": "#10B981",
        "error": "#EF4444",
        "warning": "#F59E0B",
        "neutral": "#404040",
        "text_btn": "#ffffff",
        "text_dim": "#6B7280",
    }
}

class QuizApp:
    def __init__(self, page: ft.Page):
        self.page = page
        self.page.title = "Idiom Master Pro"
        self.page.padding = 0
        self.page.theme_mode = ft.ThemeMode.SYSTEM
        
        # -- State --
        self.raw_df = None
        self.quiz_df = None
        self.n = 0
        self.current = 0
        self.selected_answers = [] 
        self.temp_selection = None 
        self.review_flags = []
        self.timer_seconds = 0
        self.time_limit_val = 0 
        self.timer_running = False
        self.submitted = False
        self.timer_thread = None
        self.timer_mode = "overall" 

        # -- UI References --
        self.file_picker = ft.FilePicker(on_result=self.on_file_picked)
        self.page.overlay.append(self.file_picker)
        
        # --- Controls ---
        self.lbl_timer = ft.Text("00:00", color=ft.Colors.RED, size=24, weight=ft.FontWeight.BOLD, font_family="Roboto Mono")
        self.lbl_mode_display = ft.Text("", size=12, color=ft.Colors.GREY, weight=ft.FontWeight.BOLD) 
        self.lbl_qnum = ft.Text("Question 1", weight=ft.FontWeight.BOLD, color=ft.Colors.GREY)
        self.lbl_question = ft.Text(size=22, weight=ft.FontWeight.W_500)
        self.lbl_feedback = ft.Text(size=15, selectable=True)
        self.lbl_stats = ft.Text("", size=14, color=ft.Colors.GREY)
        
        self.nav_grid = ft.GridView(
            expand=True,
            runs_count=5,
            max_extent=60,
            child_aspect_ratio=1.2,
            spacing=8,
            run_spacing=8,
        )

        self.option_buttons = {}
        self.opts_column = ft.Column(spacing=10)

        # Bottom Bar Buttons
        self.btn_prev = self._make_bottom_btn("Previous", ft.Icons.ARROW_BACK, self.prev_q, visible=True, bgcolor=ft.Colors.BLUE)
        self.btn_next = self._make_bottom_btn("Next", ft.Icons.ARROW_FORWARD, self.next_q, visible=True, bgcolor=ft.Colors.BLUE)

        self.btn_mark = self._make_bottom_btn("Mark Review", ft.Icons.FLAG_OUTLINED, self.toggle_flag, visible=True, bgcolor=ft.Colors.ORANGE)
        self.btn_check = self._make_bottom_btn("Check Answer", ft.Icons.CHECK_CIRCLE_OUTLINE, self.submit_current, visible=True, bgcolor=ft.Colors.GREEN)
        self.btn_finish = self._make_bottom_btn("Finish Quiz", ft.Icons.DONE_ALL, self.submit_all, visible=True, bgcolor=ft.Colors.RED)
        
        self.btn_retry = self._make_bottom_btn("Retry", ft.Icons.REFRESH, self.handle_retry, visible=False, bgcolor=ft.Colors.RED)
        self.btn_new = self._make_bottom_btn("New File", ft.Icons.UPLOAD_FILE, self.handle_new, visible=False, bgcolor=ft.Colors.PURPLE)
        # Updated to use page.window.close() for newer Flet versions
        self.btn_exit = self._make_bottom_btn("Exit", ft.Icons.EXIT_TO_APP, lambda e: self.page.window.close(), visible=False, bgcolor=ft.Colors.GREY)

        self.controls_running = [self.btn_mark, self.btn_check, self.btn_finish]
        self.controls_finished = [self.btn_retry, self.btn_new, self.btn_exit]

        self.start_view = ft.Container()
        self.quiz_view = ft.Container()
        
        self.init_ui()

    def _get_color(self, key):
        mode = "dark" if self.page.theme_mode == ft.ThemeMode.DARK else "light"
        return THEME_COLORS[mode].get(key, ft.Colors.BLACK)

    def _make_bottom_btn(self, text, icon, cmd, visible=False, bgcolor=None):
        # Centralized button factory that allows optional background color
        style = ft.ButtonStyle(
            shape=ft.RoundedRectangleBorder(radius=10),
            padding=15,
        )
        if bgcolor is not None:
            style = ft.ButtonStyle(
                shape=ft.RoundedRectangleBorder(radius=10),
                padding=15,
                bgcolor=bgcolor,
                color=ft.Colors.WHITE
            )
        return ft.ElevatedButton(
            text=text,
            icon=icon,
            on_click=cmd,
            height=45,
            style=style,
            visible=visible
        )
    
    def init_ui(self):
        # --- 1. START SCREEN ---
        self.input_seed = ft.TextField(label="Seed (Optional)", width=150, text_align=ft.TextAlign.CENTER)
        self.input_timer = ft.TextField(label="Seconds", value="30", width=100, keyboard_type=ft.KeyboardType.NUMBER, text_align=ft.TextAlign.CENTER)
        
        self.switch_mode = ft.Switch(label="Per Question Mode", value=False, on_change=self.on_mode_switch_change)
        self.switch_theme_start = ft.Switch(label="Dark Mode", value=False, on_change=self.toggle_theme)

        # New button for retrying with the same file
        self.btn_start_existing = ft.ElevatedButton(
            "Start Quiz (Current File)",
            icon=ft.Icons.PLAY_ARROW,
            on_click=lambda _: self.setup_game(), 
            height=50,
            style=ft.ButtonStyle(bgcolor=ft.Colors.GREEN, color=ft.Colors.WHITE),
            visible=False 
        )

        self.start_view = ft.Container(
            alignment=ft.alignment.center,
            expand=True,
            content=ft.Column(
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Icon(ft.Icons.SCHOOL, size=80, color=ft.Colors.BLUE),
                    ft.Text("Idiom Master 🎓", size=32, weight=ft.FontWeight.BOLD),
                    ft.Text("Tablet Edition", color=ft.Colors.GREY),
                    ft.Container(height=30),
                    
                    ft.ElevatedButton(
                        "Select File (Excel/CSV)",
                        icon=ft.Icons.UPLOAD_FILE,
                        on_click=lambda _: self.file_picker.pick_files(allowed_extensions=["csv", "xlsx", "xls"]),
                        height=50,
                        style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE, color=ft.Colors.WHITE)
                    ),
                    
                    self.btn_start_existing,
                    
                    ft.Container(height=30),
                    ft.Container(
                        padding=20,
                        border_radius=15,
                        content=ft.Column([
                            ft.Text("Configuration", weight=ft.FontWeight.BOLD),
                            ft.Row([self.input_seed, self.input_timer], alignment=ft.MainAxisAlignment.CENTER),
                            self.switch_mode,
                            self.switch_theme_start
                        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=15)
                    )
                ]
            )
        )

        # --- 2. QUIZ SCREEN ---
        self.switch_theme_quiz = ft.Switch(value=False, on_change=self.toggle_theme)
        self.header_container = ft.Container(
            padding=ft.padding.symmetric(horizontal=20, vertical=10),
            content=ft.Row([
                ft.Column([
                    ft.Text("Idiom Master", size=24, weight=ft.FontWeight.BOLD),
                    self.lbl_mode_display
                ], spacing=0),
                ft.Row([
                    ft.Text("Dark Mode"), 
                    self.switch_theme_quiz,
                    ft.Container(width=20),
                    self.lbl_timer
                ])
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)
        )

        self.q_card = ft.Container(
            padding=30,
            border_radius=15,
            content=self.lbl_question
        )

        for char in ["A", "B", "C", "D"]:
            btn = ft.OutlinedButton(
                text=f"{char}.",
                on_click=lambda e, c=char: self.on_option_click(c),
                style=ft.ButtonStyle(
                    shape=ft.RoundedRectangleBorder(radius=8),
                    padding=20,
                    alignment=ft.alignment.center_left
                )
            )
            self.option_buttons[char] = btn
            self.opts_column.controls.append(btn)

        self.feedback_container = ft.Container(
            visible=False,
            padding=15,
            border=ft.border.all(1, ft.Colors.GREY),
            border_radius=10,
            content=self.lbl_feedback
        )

        left_panel = ft.Column(
            expand=2,
            scroll=ft.ScrollMode.AUTO,
            controls=[
                self.lbl_qnum,
                self.q_card,
                ft.Container(height=20),
                self.opts_column,
                ft.Container(height=20),
                ft.Container(
            expand=True,
            content=self.feedback_container
        )
            ]
        )

        right_panel = ft.Container(
            expand=1,
            padding=10,
            content=ft.Column([
                ft.Text("Navigator", weight=ft.FontWeight.BOLD),
                ft.Divider(),
                self.nav_grid,
                ft.Divider(),
                self.lbl_stats
            ])
        )

        self.bottom_bar_container = ft.Container(
            padding=15,
            content=ft.Row([
                ft.Row([self.btn_mark, self.btn_prev, self.btn_check, self.btn_next, self.btn_retry, self.btn_new]),
                ft.Container(expand=True),
                ft.Row([self.btn_finish, self.btn_exit])
            ])
        )

        self.split_container = ft.Container(
            expand=True,
            padding=20,
            content=ft.Row(
                vertical_alignment=ft.CrossAxisAlignment.START,
                controls=[
                    left_panel,
                    ft.VerticalDivider(width=1, color=ft.Colors.GREY_300),
                    right_panel
                ]
            )
        )

        self.quiz_view = ft.Column(
            expand=True,
            spacing=0,
            controls=[
                self.header_container,
                self.split_container,
                self.bottom_bar_container
            ],
            visible=False
        )

        self.page.add(self.start_view, self.quiz_view)
        self.apply_theme_colors()

    # --- THEME & MODE LOGIC ---
    def toggle_theme(self, e):
        val = e.control.value
        self.page.theme_mode = ft.ThemeMode.DARK if val else ft.ThemeMode.LIGHT
        self.switch_theme_start.value = val
        self.switch_theme_quiz.value = val
        self.apply_theme_colors()
        self.page.update()

    def on_mode_switch_change(self, e):
        self.timer_mode = "per_question" if e.control.value else "overall"

    def apply_theme_colors(self):
        bg = self._get_color("bg_main")
        card = self._get_color("card_bg")
        text = self._get_color("text")
        
        self.page.bgcolor = bg
        self.start_view.bgcolor = bg
        self.split_container.bgcolor = bg
        self.start_view.content.controls[-1].bgcolor = card
        self.header_container.bgcolor = card
        self.bottom_bar_container.bgcolor = card
        self.q_card.bgcolor = card
        self.lbl_question.color = text
        self.lbl_timer.color = self._get_color("error")
        self.lbl_feedback.color = text
        
        if self.quiz_view.visible:
            self.load_question(self.current)
        
        self.update_nav_colors()

    # --- GAME LOGIC ---
    def on_file_picked(self, e: ft.FilePickerResultEvent):
        if not e.files: return
        file_path = e.files[0].path
        if not file_path:
             self.page.open(ft.SnackBar(ft.Text("Error: PC cannot read phone file path. Build APK to test.")))
             return

        try:
            self.raw_df = pd.read_csv(file_path) if file_path.endswith(".csv") else pd.read_excel(file_path)
            self.setup_game()
        except Exception as ex:
            self.page.open(ft.SnackBar(ft.Text(f"Error loading file: {ex}")))

    def setup_game(self):
        try:
            seed_val = self.input_seed.value.strip()
            seed = int(seed_val) if seed_val else None
            
            if self.raw_df is None:
                raise ValueError("No file loaded. Please select a file.")

            self.quiz_df = self._generate_quiz_from_idioms(self.raw_df, seed=seed)
            self.n = len(self.quiz_df)
            self.selected_answers = [None] * self.n
            self.review_flags = [False] * self.n
            self.current = 0
            self.submitted = False
            self.temp_selection = None 
            
            self.nav_grid.controls.clear()
            for i in range(self.n):
                self.nav_grid.controls.append(
                    ft.Container(
                        content=ft.Text(str(i+1), weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
                        alignment=ft.alignment.center,
                        border_radius=5,
                        on_click=lambda e, x=i: self.jump_to(x),
                        data=i 
                    )
                )
            
            try:
                self.time_limit_val = int(self.input_timer.value)
            except:
                self.time_limit_val = 30
            
            if self.time_limit_val <= 0:
                self.time_limit_val = 30

            self.timer_seconds = self.time_limit_val
            self.timer_mode = "per_question" if self.switch_mode.value else "overall"
            self.lbl_mode_display.value = f"Mode: {self.timer_mode.replace('_', ' ').title()}"
            self.timer_running = True
            
            self.start_timer_thread()

            self.start_view.visible = False
            self.quiz_view.visible = True
            self.toggle_controls(finished=False)
            self.apply_theme_colors()
            
            self.load_question(0)
            self.page.update()
        except Exception as ex:
             self.page.open(ft.SnackBar(ft.Text(f"Setup Error: {ex}")))

    def load_question(self, idx):
        if not (0 <= idx < self.n): return
        
        # FIX: Reset temp selection when moving to any new question
        if idx != self.current:
            self.temp_selection = None
            
        self.current = idx
        
        row = self.quiz_df.iloc[idx]
        self.lbl_qnum.value = f"Question {idx + 1} of {self.n}"
        self.lbl_question.value = row["Question"]
        
        committed_ans = self.selected_answers[idx]
        correct_letter = row["Correct Answer"]
        show_answers = self.submitted or (committed_ans is not None)
        
        for char, btn in self.option_buttons.items():
            btn.text = f"{char}. {row[f'Option {char}']}"
            btn.style.bgcolor = None
            btn.style.side = ft.BorderSide(1, self._get_color("neutral"))
            btn.style.color = self._get_color("text_btn") 
            btn.disabled = False

            if show_answers:
                btn.disabled = True
                if char == correct_letter:
                    btn.style.bgcolor = self._get_color("success")
                    btn.style.color = ft.Colors.WHITE
                    btn.text += "  ✅"
                elif char == committed_ans and char != correct_letter:
                    btn.style.bgcolor = self._get_color("error")
                    btn.style.color = ft.Colors.WHITE
                    btn.text += "  ❌"
                else:
                    btn.style.side = ft.BorderSide(1, ft.Colors.GREY_400) 
            else:
                # Visual highlight ONLY for temp selection
                is_selected = (self.selected_answers[idx] is None) and (char == self.temp_selection)
                
                if is_selected:
                    btn.style.bgcolor = self._get_color("accent")
                    btn.style.color = ft.Colors.WHITE

        if show_answers:
            self.feedback_container.visible = True
            if committed_ans:
                is_correct = (committed_ans == correct_letter)
                status_txt = "Correct! 🎉" if is_correct else "Incorrect."
                status_color = self._get_color("success") if is_correct else self._get_color("error")
            else:
                status_txt = "Not Answered."
                status_color = self._get_color("warning")

            full_text = f"{status_txt}\n\nDefinitions:\n"
            for opt in ["A", "B", "C", "D"]:
                idiom = row[f"Option {opt}"]
                meaning = row[f"Meaning {opt}"]
                marker = "➡"
                if opt == correct_letter:
                    marker = "✅ ➡"
                elif opt == committed_ans:
                    marker = "➡"
                full_text += f"{opt}: {idiom}\n   {marker} {meaning}\n\n"
            
            self.lbl_feedback.value = full_text
            self.lbl_feedback.color = self._get_color("text")
        else:
            self.feedback_container.visible = False

        self.update_nav_colors()
        self.page.update()

    def on_option_click(self, char):
        if self.submitted: return
        # Prevent changing if already answered
        if self.selected_answers[self.current]:
            return

        self.temp_selection = char
        self.load_question(self.current)

    def submit_current(self, e=None, auto=False):
        # Prevent submission if quiz already finished or question already answered
        if self.submitted or self.selected_answers[self.current]:
            return

        # Decide whether this is an automatic submit (timeout) or a manual one
        # auto=True explicitly indicates automatic (timeout) submission.
        # If auto is True, do NOT commit temp_selection.
        if auto:
            selection_to_commit = None
        else:
            # Manual submit (user clicked "Check Answer")
            selection_to_commit = self.temp_selection

        # If user tried to submit manually without selecting, show snackbar and stop.
        if not selection_to_commit:
            if not auto:
                # manual empty submit -> show message
                self.page.open(ft.SnackBar(ft.Text("Please select an option first.")))
                return
            # else: auto submit with no answer, continue

        # Commit the answer (could be None for auto-timeout = not answered)
        self.selected_answers[self.current] = selection_to_commit

        if self.timer_mode == "per_question":
            # stop this question's timer
            self.timer_running = False

        # Refresh view to show feedback (or "Not Answered." for None)
        self.load_question(self.current)

        # In per-question mode, move to next question after a short pause so user sees feedback
        if self.timer_mode == "per_question":
            def delayed_move():
                time.sleep(1.5)
                async def move_next():
                    self.next_q(None)
                self.page.run_task(move_next)
            threading.Thread(target=delayed_move, daemon=True).start()

    def next_q(self, e):
        if self.current < self.n - 1:
            self.temp_selection = None
            self.current += 1
            
            if self.timer_mode == "per_question" and not self.submitted:
                self.timer_seconds = self.time_limit_val
                self.timer_running = True
                m, s = divmod(self.timer_seconds, 60)
                self.lbl_timer.value = f"{m:02d}:{s:02d}"
                self.lbl_timer.update()

                if self.timer_thread is None or not self.timer_thread.is_alive():
                    self.start_timer_thread()
            
            self.load_question(self.current)

    def prev_q(self, e):
        if self.timer_mode == "per_question" and not self.submitted:
            self.page.open(ft.SnackBar(ft.Text("Cannot go back in Per-Question Mode.")))
            return
            
        if self.current > 0:
            self.temp_selection = None
            self.current -= 1
            self.load_question(self.current)

    def jump_to(self, idx):
        if self.timer_mode == "per_question" and not self.submitted:
            self.page.open(ft.SnackBar(ft.Text("Navigator locked in Per-Question Mode.")))
            return
        
        self.temp_selection = None
        self.load_question(idx)

    def toggle_flag(self, e):
        if self.submitted: return
        self.review_flags[self.current] = not self.review_flags[self.current]
        self.update_nav_colors()
        self.page.update()

    def update_nav_colors(self):
        for i, box in enumerate(self.nav_grid.controls):
            bg = self._get_color("neutral")
            is_reviewed = self.review_flags[i]
            is_current = (i == self.current)
            is_answered = (self.selected_answers[i] is not None)

            if self.submitted:
                if not is_answered:
                    bg = self._get_color("error")
                else:
                    correct = self.quiz_df.iloc[i]["Correct Answer"]
                    sel = self.selected_answers[i]
                    bg = self._get_color("success") if sel == correct else self._get_color("error")
                if is_current: bg = self._get_color("accent")
            else:
                if is_answered:
                    correct = self.quiz_df.iloc[i]["Correct Answer"]
                    sel = self.selected_answers[i]
                    bg = self._get_color("success") if sel == correct else self._get_color("error")
                
                if is_current:
                    bg = self._get_color("accent")
                elif is_reviewed and not is_answered:
                    bg = self._get_color("warning")
            
            box.bgcolor = bg
        if self.nav_grid.page: self.nav_grid.update()

    def submit_all(self, e=None):
        self.submitted = True
        self.timer_running = False
        
        # Calculate Stats
        total = self.n
        attempted = sum(1 for a in self.selected_answers if a is not None)
        correct = sum(1 for i in range(self.n) if self.selected_answers[i] == self.quiz_df.iloc[i]["Correct Answer"])
        wrong = attempted - correct
        marked = sum(self.review_flags)
        
        self.lbl_stats.value = f"Score: {correct} / {total}"
        
        dlg = ft.AlertDialog(
            title=ft.Text("Quiz Results 📊", weight=ft.FontWeight.BOLD),
            content=ft.Column([
                ft.Row([ft.Icon(ft.Icons.LIST_ALT), ft.Text(f"Total Questions: {total}", size=16)]),
                ft.Row([ft.Icon(ft.Icons.CHECK_CIRCLE, color=ft.Colors.GREEN), ft.Text(f"Correct: {correct}", size=16, color=ft.Colors.GREEN)]),
                ft.Row([ft.Icon(ft.Icons.CANCEL, color=ft.Colors.RED), ft.Text(f"Wrong: {wrong}", size=16, color=ft.Colors.RED)]),
                ft.Row([ft.Icon(ft.Icons.EDIT), ft.Text(f"Attempted: {attempted}", size=16)]),
                ft.Row([ft.Icon(ft.Icons.FLAG, color=ft.Colors.ORANGE), ft.Text(f"Marked: {marked}", size=16, color=ft.Colors.ORANGE)]),
            ], tight=True, spacing=10),
            actions=[
                ft.TextButton("Review Answers", on_click=lambda e: self.page.close(dlg))
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self.page.open(dlg)
        
        self.toggle_controls(finished=True)
        self.load_question(self.current)

    def toggle_controls(self, finished):
        for btn in self.controls_running:
            btn.visible = not finished
        for btn in self.controls_finished:
            btn.visible = finished
        self.page.update()

    def handle_retry(self, e):
        self.quiz_view.visible = False
        self.start_view.visible = True
        self.btn_start_existing.visible = True
        self.page.update()
    
    def handle_new(self, e):
        self.quiz_view.visible = False
        self.start_view.visible = True
        self.btn_start_existing.visible = False
        self.page.update()

    def start_timer_thread(self):
        self.timer_running = True
        def run():
            while self.timer_running:
                if self.timer_seconds > 0:
                    time.sleep(1)
                    self.timer_seconds -= 1
                    m, s = divmod(self.timer_seconds, 60)
                    self.lbl_timer.value = f"{m:02d}:{s:02d}"
                    self.lbl_timer.update()
                else:
                    if self.timer_mode == "overall":
                        self.timer_running = False
                        async def finish(): self.submit_all()
                        self.page.run_task(finish)
                        break
                    elif self.timer_mode == "per_question":
                        # STOP: automatic per-question submit — use auto=True so temp_selection isn't committed
                        self.timer_running = False
                        async def auto_submit():
                            self.submit_current(None, auto=True)
                        self.page.run_task(auto_submit)
                        break
                        
        self.timer_thread = threading.Thread(target=run, daemon=True)
        self.timer_thread.start()

    def _generate_quiz_from_idioms(self, raw_df, seed=None):
        idiom_col = next((c for c in raw_df.columns if "idiom" in c.lower()), None)
        meaning_col = next((c for c in raw_df.columns if "meaning" in c.lower()), None)
        if not idiom_col or not meaning_col: raise ValueError("Need 'idiom' and 'meaning' cols")

        if seed is not None:
            shuffled = raw_df.sample(frac=1, random_state=seed).reset_index(drop=True)
            rng = random.Random(seed)
        else:
            shuffled = raw_df.sample(frac=1).reset_index(drop=True)
            rng = random.Random()

        if len(shuffled) < 4: 
            while len(shuffled) < 4: shuffled = pd.concat([shuffled, shuffled])
        
        quiz_data = []
        for i in range(0, len(shuffled), 4):
            chunk = shuffled.iloc[i : i + 4]
            if len(chunk) < 4:
                chunk = pd.concat([chunk, shuffled.iloc[0:4-len(chunk)]])

            if len(chunk) == 4:
                target = chunk.iloc[0]
                opts = [{"idiom": target[idiom_col], "meaning": target[meaning_col], "is_correct": True}]
                for _, r in chunk.iloc[1:].iterrows():
                    opts.append({"idiom": r[idiom_col], "meaning": r[meaning_col], "is_correct": False})
                rng.shuffle(opts)
                
                entry = {"Question": f"{target[meaning_col]}", "Correct Answer": ""}
                for idx, char in enumerate(["A", "B", "C", "D"]):
                    entry[f"Option {char}"] = opts[idx]["idiom"]
                    entry[f"Meaning {char}"] = opts[idx]["meaning"]
                    if opts[idx]["is_correct"]: entry["Correct Answer"] = char
                quiz_data.append(entry)
        return pd.DataFrame(quiz_data)

def main(page: ft.Page):
    QuizApp(page)

ft.app(target=main)

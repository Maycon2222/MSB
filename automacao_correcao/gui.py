from pathlib import Path
import ctypes
import threading
import traceback
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from automacao_correcao.operations.danfe_pdf import generate_danfes_for_files_safe
from automacao_correcao.operations.product_analysis import analyze_xml_products_to_xlsx
from automacao_correcao.operations.sieg_reports import (
    clean_bm026_with_existing_reports,
    download_sieg_and_clean_bm026,
)
from automacao_correcao.operations.xml_nfe import (
    FIXED_REASON_OPTIONS,
    fixed_reason_reference_rows_to_xlsx,
    fixed_reason_xml_files,
    nfe_folder_to_xlsx,
    old_references_to_xlsx,
    reference_rows_when_inf_cpl_matches_to_xlsx,
    xml_files,
)


def safe_folder_name(value: str) -> str:
    safe = "".join(char if char.isalnum() or char in {" ", "_", "-"} else "_" for char in value.strip())
    return safe.strip() or "resultado"


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("AutomaÃ§Ãµes MSB")
        self.geometry("900x560")
        self.minsize(820, 500)
        self.maxsize(900, 560)
        self.resizable(False, False)
        self.configure(bg="#f4f7fb")
        self._set_app_identity()
        self._set_window_icon()

        self.input_path = tk.StringVar()
        self.output_path = tk.StringVar()
        self.search_text = tk.StringVar()
        self.reason_type = tk.StringVar(value="vencimento")
        self.months_limit = tk.StringVar(value="5")
        self.status = tk.StringVar(value="Pronto")
        self.sieg_database_password = tk.StringVar()
        self.sieg_bm026_path = tk.StringVar()
        self.sieg_output_path = tk.StringVar()
        self.sieg_cancel_path = tk.StringVar()
        self.sieg_descon_path = tk.StringVar()
        self.analysis_xml_path = tk.StringVar()
        self.analysis_shelf_path = tk.StringVar(value=str(self.default_shelf_json()))
        self.analysis_output_path = tk.StringVar()

        self._build()

    def _asset_path(self, name: str) -> Path:
        return Path(__file__).resolve().parent / "assets" / name

    def default_shelf_json(self) -> Path:
        return Path(__file__).resolve().parent / "data" / "produtos_queijos_shelf.json"

    def _set_app_identity(self) -> None:
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("MSB.Automacoes")
        except Exception:
            pass

    def _set_window_icon(self) -> None:
        icon_path = self._asset_path("msb_icon.ico")
        png_path = self._asset_path("msb_icon.png")
        try:
            if icon_path.exists():
                self.iconbitmap(str(icon_path))
            if png_path.exists():
                self.icon_photo = tk.PhotoImage(file=str(png_path))
                self.iconphoto(True, self.icon_photo)
        except Exception:
            pass

    def _configure_style(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(".", font=("Segoe UI", 10), background="#f4f7fb", foreground="#162033")
        style.configure("TFrame", background="#ffffff")
        style.configure("Root.TFrame", background="#f4f7fb")
        style.configure("Header.TFrame", background="#163b5c")
        style.configure("HeaderTitle.TLabel", background="#163b5c", foreground="#ffffff", font=("Segoe UI", 18, "bold"))
        style.configure("HeaderSub.TLabel", background="#163b5c", foreground="#d7e7f5", font=("Segoe UI", 10))
        style.configure("Panel.TFrame", background="#ffffff", relief="flat")
        style.configure("Actions.TFrame", background="#ffffff")
        style.configure("PanelTitle.TLabel", background="#ffffff", foreground="#163b5c", font=("Segoe UI", 12, "bold"))
        style.configure("Muted.TLabel", background="#ffffff", foreground="#617089")
        style.configure("Field.TLabel", background="#ffffff", foreground="#233044", font=("Segoe UI", 9, "bold"))
        style.configure("TNotebook", background="#f4f7fb", borderwidth=0)
        style.configure("TNotebook.Tab", padding=(18, 10), background="#e7edf5", foreground="#334155")
        style.map("TNotebook.Tab", background=[("selected", "#ffffff")], foreground=[("selected", "#163b5c")])
        style.configure("TEntry", padding=7, fieldbackground="#fbfdff")
        style.configure("TSpinbox", padding=6, fieldbackground="#fbfdff")
        style.configure("TButton", padding=(12, 8), background="#e6edf5", foreground="#172033", borderwidth=0)
        style.map("TButton", background=[("active", "#d7e2ef")])
        style.configure("Primary.TButton", background="#1f6feb", foreground="#ffffff", font=("Segoe UI", 10, "bold"))
        style.map("Primary.TButton", background=[("active", "#175ec9")], foreground=[("active", "#ffffff")])
        style.configure("Accent.TButton", background="#0f766e", foreground="#ffffff", font=("Segoe UI", 10, "bold"))
        style.map("Accent.TButton", background=[("active", "#0b5f59")], foreground=[("active", "#ffffff")])
        style.configure("Status.TLabel", background="#eaf1f8", foreground="#314158", padding=(10, 7))

    def _build(self) -> None:
        self._configure_style()

        root = ttk.Frame(self, padding=18, style="Root.TFrame")
        root.pack(fill="both", expand=True)

        header = ttk.Frame(root, padding=(18, 16), style="Header.TFrame")
        header.pack(fill="x", pady=(0, 14))
        ttk.Label(header, text="AutomaÃ§Ãµes MSB", style="HeaderTitle.TLabel").pack(anchor="w")
        ttk.Label(
            header,
            text="Trate XMLs e planilhas com selecao por clique e saida em Excel.",
            style="HeaderSub.TLabel",
        ).pack(anchor="w", pady=(4, 0))

        self.tabs = ttk.Notebook(root)
        self.tabs.pack(fill="both", expand=True)

        self._build_xml_tab()
        self._build_xml_analysis_tab()
        self._build_sieg_tab()

        status = ttk.Label(root, textvariable=self.status, anchor="w", style="Status.TLabel")
        status.pack(fill="x", pady=(12, 0))

    def _build_xml_tab(self) -> None:
        tab = ttk.Frame(self.tabs, padding=18, style="Panel.TFrame")
        self.tabs.add(tab, text="XML NF-e")

        ttk.Label(tab, text="XML NF-e", style="PanelTitle.TLabel").grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(
            tab,
            text="Selecione um XML unico ou uma pasta inteira. Depois escolha a acao desejada.",
            style="Muted.TLabel",
        ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(4, 18))

        self._path_row(
            tab,
            row=2,
            label="Arquivo XML ou pasta",
            variable=self.input_path,
            commands=[
                ("Arquivo", self.select_xml_file),
                ("Pasta", self.select_folder),
            ],
        )
        self._path_row(
            tab,
            row=3,
            label="Planilha de saida",
            variable=self.output_path,
            commands=[("Salvar como", self.select_output_xlsx)],
        )

        ttk.Label(tab, text="Motivo", style="Field.TLabel").grid(row=4, column=0, sticky="w", pady=(18, 6))
        reason_box = ttk.Combobox(
            tab,
            textvariable=self.reason_type,
            values=FIXED_REASON_OPTIONS,
            state="readonly",
        )
        reason_box.grid(row=4, column=1, columnspan=2, sticky="ew", pady=(18, 6))
        reason_box.bind("<<ComboboxSelected>>", lambda _event: self.update_manual_reason_state())

        self.manual_reason_label = ttk.Label(tab, text="Texto na Observacao", style="Field.TLabel")
        self.manual_reason_label.grid(row=5, column=0, sticky="w", pady=6)
        self.manual_reason_entry = ttk.Entry(tab, textvariable=self.search_text, state="disabled")
        self.manual_reason_entry.grid(row=5, column=1, columnspan=2, sticky="ew", pady=6)

        ttk.Label(tab, text="Referencia antiga acima de meses", style="Field.TLabel").grid(row=6, column=0, sticky="w", pady=6)
        ttk.Spinbox(tab, from_=1, to=60, textvariable=self.months_limit, width=8).grid(
            row=6, column=1, sticky="w", pady=6
        )

        buttons = ttk.Frame(tab, padding=(0, 8, 0, 8), style="Actions.TFrame")
        buttons.grid(row=7, column=0, columnspan=3, sticky="ew", pady=(8, 6))

        ttk.Button(
            buttons,
            text="Converter XML completo",
            command=lambda: self.run_task(self.convert_full_xml),
        ).pack(side="left", padx=(0, 10))
        ttk.Button(
            buttons,
            text="Gerar referencias antigas",
            command=lambda: self.run_task(self.old_references),
            style="Accent.TButton",
        ).pack(side="left", padx=10)
        ttk.Button(
            buttons,
            text="Buscar observacao",
            command=self.confirm_and_run_search_reason,
            style="Primary.TButton",
        ).pack(side="left", padx=10)

        tab.columnconfigure(1, weight=1)
        self.update_manual_reason_state()

    def _build_xml_analysis_tab(self) -> None:
        tab = ttk.Frame(self.tabs, padding=18, style="Panel.TFrame")
        self.tabs.add(tab, text="Analise XML")

        ttk.Label(tab, text="Analise XML", style="PanelTitle.TLabel").grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(
            tab,
            text="Classifica notas por referencia antiga, vencimento, diferenca de peso e analise logistica.",
            style="Muted.TLabel",
        ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(4, 18))

        self._path_row(
            tab,
            row=2,
            label="Arquivo XML ou pasta",
            variable=self.analysis_xml_path,
            commands=[
                ("Arquivo", self.select_analysis_xml_file),
                ("Pasta", self.select_analysis_xml_folder),
            ],
        )
        self._path_row(
            tab,
            row=3,
            label="Shelf produtos",
            variable=self.analysis_shelf_path,
            commands=[("Selecionar", self.select_analysis_shelf_file)],
        )
        self._path_row(
            tab,
            row=4,
            label="Relatorio de saida",
            variable=self.analysis_output_path,
            commands=[("Salvar como", self.select_analysis_output_xlsx)],
        )

        ttk.Button(
            tab,
            text="Analisar motivos dos XMLs",
            command=lambda: self.run_task(self.run_xml_reason_analysis),
            style="Primary.TButton",
        ).grid(row=5, column=0, columnspan=3, sticky="w", pady=(20, 10))

        tab.columnconfigure(1, weight=1)
    def _build_sieg_tab(self) -> None:
        tab = ttk.Frame(self.tabs, padding=18, style="Panel.TFrame")
        self.tabs.add(tab, text="SIEG")

        ttk.Label(tab, text="SIEG + BM026", style="PanelTitle.TLabel").grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(
            tab,
            text="Baixa cancel/descon do SIEG, trata o descon e limpa o relatorio BM026.",
            style="Muted.TLabel",
        ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(4, 18))

        self._path_row(
            tab,
            row=2,
            label="Relatorio BM026 / All",
            variable=self.sieg_bm026_path,
            commands=[("Selecionar", self.select_sieg_bm026_file)],
        )
        self._path_row(
            tab,
            row=3,
            label="Planilha limpa de saida",
            variable=self.sieg_output_path,
            commands=[("Salvar como", self.select_sieg_output_xlsx)],
        )
        self._path_row(
            tab,
            row=4,
            label="Cancel baixado",
            variable=self.sieg_cancel_path,
            commands=[("Selecionar", self.select_sieg_cancel_file)],
        )
        self._path_row(
            tab,
            row=5,
            label="Descon baixado",
            variable=self.sieg_descon_path,
            commands=[("Selecionar", self.select_sieg_descon_file)],
        )

        ttk.Label(tab, text="Senha do banco", style="Field.TLabel").grid(row=6, column=0, sticky="w", pady=7)
        ttk.Entry(tab, textvariable=self.sieg_database_password, show="*").grid(
            row=6,
            column=1,
            sticky="ew",
            padx=10,
            pady=7,
        )

        ttk.Button(
            tab,
            text="Criar nuvem",
            command=self.confirm_and_run_sieg,
            style="Primary.TButton",
        ).grid(row=6, column=2, sticky="e", pady=7)

        tab.columnconfigure(1, weight=1)

    def _path_row(self, parent, row: int, label: str, variable: tk.StringVar, commands) -> None:
        ttk.Label(parent, text=label, style="Field.TLabel").grid(row=row, column=0, sticky="w", pady=7)
        ttk.Entry(parent, textvariable=variable).grid(row=row, column=1, sticky="ew", padx=10, pady=7)
        button_frame = ttk.Frame(parent)
        button_frame.grid(row=row, column=2, sticky="e", pady=7)
        for text, command in commands:
            ttk.Button(button_frame, text=text, command=command).pack(side="left", padx=(0, 8))

    def select_xml_file(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("XML", "*.xml"), ("Todos", "*.*")])
        if path:
            self.input_path.set(path)

    def select_folder(self) -> None:
        path = filedialog.askdirectory()
        if path:
            self.input_path.set(path)

    def select_output_xlsx(self) -> str:
        path = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("Excel", "*.xlsx")],
            initialfile=self.default_output_name(),
        )
        if path:
            self.output_path.set(path)
        return path

    def select_sieg_bm026_file(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("Planilhas", "*.xlsx *.xls *.csv"), ("Todos", "*.*")])
        if path:
            self.sieg_bm026_path.set(path)

    def select_sieg_output_xlsx(self) -> str:
        path = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("Excel", "*.xlsx")],
            initialfile="BM026_limpo.xlsx",
        )
        if path:
            self.sieg_output_path.set(path)
        return path

    def select_sieg_cancel_file(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("Planilhas", "*.xlsx *.xls"), ("Todos", "*.*")])
        if path:
            self.sieg_cancel_path.set(path)

    def select_sieg_descon_file(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("Planilhas", "*.xlsx *.xls"), ("Todos", "*.*")])
        if path:
            self.sieg_descon_path.set(path)

    def select_analysis_xml_file(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("XML", "*.xml"), ("Todos", "*.*")])
        if path:
            self.analysis_xml_path.set(path)

    def select_analysis_xml_folder(self) -> None:
        path = filedialog.askdirectory()
        if path:
            self.analysis_xml_path.set(path)

    def select_analysis_shelf_file(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("Shelf", "*.xlsx *.xls *.json"), ("Todos", "*.*")])
        if path:
            self.analysis_shelf_path.set(path)

    def select_analysis_output_xlsx(self) -> str:
        path = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("Excel", "*.xlsx")],
            initialfile="analise_motivos_xml.xlsx",
        )
        if path:
            self.analysis_output_path.set(path)
        return path
    def default_output_name(self) -> str:
        selected_tab = self.tabs.tab(self.tabs.select(), "text")
        if selected_tab == "Analise XML":
            return "analise_motivos_xml.xlsx"
        if selected_tab == "XML NF-e" and self.reason_type.get().strip():
            reason = self.reason_type.get().strip()
            if reason != "outros":
                return f"{reason}.xlsx"
        if self.search_text.get().strip():
            safe_text = "".join(
                char if char.isalnum() or char in {" ", "_", "-"} else "_"
                for char in self.search_text.get().strip()
            ).strip()
            return f"{safe_text}.xlsx"
        return "resultado.xlsx"

    def ensure_output_path(self, output_path: str, selector) -> str:
        if output_path.strip():
            return output_path
        selected = selector()
        if not selected:
            raise ValueError("Escolha onde salvar a planilha.")
        return selected

    def validate_paths(self, input_path: str, output_path: str) -> tuple[Path, Path]:
        source = Path(input_path)
        destination = Path(output_path)
        if not source.exists():
            raise ValueError("Selecione um arquivo ou pasta de entrada valido.")
        if not str(destination):
            raise ValueError("Selecione onde salvar a planilha.")
        return source, destination

    def run_task(self, task) -> None:
        def worker():
            try:
                self.after(0, lambda: self.status.set("Executando..."))
                result = task()
            except Exception as exc:
                error_log = Path(__file__).resolve().parent / "erro_automacoes_msb.log"
                error_log.write_text(traceback.format_exc(), encoding="utf-8")
                self.after(0, lambda: self.status.set("Erro"))
                self.after(0, lambda: messagebox.showerror("Erro", f"{exc}\n\nDetalhes salvos em:\n{error_log}"))
                return
            self.after(0, lambda: self.status.set("Concluido"))
            self.after(0, lambda: messagebox.showinfo("Concluido", str(result)))

        threading.Thread(target=worker, daemon=True).start()

    def update_manual_reason_state(self) -> None:
        state = "normal" if self.reason_type.get() == "outros" else "disabled"
        self.manual_reason_entry.configure(state=state)
        if state == "disabled":
            self.search_text.set("")

    def confirm_and_run_sieg(self) -> None:
        has_cancel = bool(self.sieg_cancel_path.get().strip())
        has_descon = bool(self.sieg_descon_path.get().strip())
        if has_cancel != has_descon:
            messagebox.showerror("Erro", "Informe as duas planilhas: cancel e descon.")
            return
        if not has_cancel and not self.sieg_database_password.get().strip():
            messagebox.showerror("Erro", "Digite a senha do banco para baixar no SIEG, ou selecione cancel/descon manualmente.")
            return
        mode = "usar as planilhas cancel/descon selecionadas" if has_cancel else "abrir o Chrome e baixar cancel/descon no SIEG"
        confirmed = messagebox.askyesno(
            "Confirmar SIEG",
            f"O sistema vai {mode}, tratar a descon e limpar o BM026 selecionado.\n\nDeseja continuar?",
        )
        if confirmed:
            self.run_task(self.run_sieg_task)

    def run_sieg_task(self) -> Path:
        output_path = self.ensure_output_path(self.sieg_output_path.get(), self.select_sieg_output_xlsx)
        source, destination = self.validate_paths(self.sieg_bm026_path.get(), output_path)
        if self.sieg_cancel_path.get().strip() and self.sieg_descon_path.get().strip():
            cancel = Path(self.sieg_cancel_path.get())
            descon = Path(self.sieg_descon_path.get())
            if not cancel.exists() or not descon.exists():
                raise ValueError("As planilhas cancel/descon selecionadas nao foram encontradas.")
            generated = clean_bm026_with_existing_reports(
                bm026_path=source,
                cancel_path=cancel,
                descon_path=descon,
                output_path=destination,
            )
        else:
            work_dir = Path(destination).with_suffix("").parent / "_sieg_downloads"
            generated = download_sieg_and_clean_bm026(
                bm026_path=source,
                output_path=destination,
                work_dir=work_dir,
                database_password=self.sieg_database_password.get(),
            )
        self.status.set(f"Concluido: BM026 limpo salvo em {generated.output_path}")
        return generated.output_path

    def run_xml_reason_analysis(self) -> Path:
        output_path = self.ensure_output_path(self.analysis_output_path.get(), self.select_analysis_output_xlsx)
        source, destination = self.validate_paths(self.analysis_xml_path.get(), output_path)
        shelf = Path(self.analysis_shelf_path.get())
        if not shelf.exists():
            raise ValueError("Selecione a planilha ou JSON de shelf.")
        generated = analyze_xml_products_to_xlsx(source, shelf, destination)
        self.status.set(f"Concluido: analise de motivos salva em {generated}")
        return generated
    def convert_full_xml(self) -> Path:
        output_path = self.ensure_output_path(self.output_path.get(), self.select_output_xlsx)
        source, destination = self.validate_paths(self.input_path.get(), output_path)
        generated_path = nfe_folder_to_xlsx(source, destination)
        danfe_dir = generated_path.parent / f"DANFEs_{safe_folder_name(generated_path.stem)}"
        generated, errors = generate_danfes_for_files_safe(xml_files(source), danfe_dir)
        self.status.set(f"Concluido: planilha, {len(generated)} DANFEs e {len(errors)} erro(s)")
        return generated_path

    def old_references(self) -> Path:
        output_path = self.ensure_output_path(self.output_path.get(), self.select_output_xlsx)
        source, destination = self.validate_paths(self.input_path.get(), output_path)
        generated_path = old_references_to_xlsx(source, destination, months_limit=int(self.months_limit.get()))
        danfe_dir = generated_path.parent / f"DANFEs_{safe_folder_name(generated_path.stem)}"
        generated, errors = generate_danfes_for_files_safe(xml_files(source), danfe_dir)
        self.status.set(f"Concluido: planilha, {len(generated)} DANFEs e {len(errors)} erro(s)")
        return generated_path

    def selected_reason_files(self) -> list[Path]:
        source = Path(self.input_path.get())
        reason = self.reason_type.get()
        if reason == "outros":
            manual_text = self.search_text.get().strip()
            if not manual_text:
                raise ValueError("Digite o texto que deseja buscar na observacao.")
            from automacao_correcao.operations.danfe_pdf import matching_xml_files_by_observation

            return matching_xml_files_by_observation(source, manual_text)
        return fixed_reason_xml_files(source, reason)

    def confirm_and_run_search_reason(self) -> None:
        if not Path(self.input_path.get()).exists():
            messagebox.showerror("Erro", "Selecione um arquivo XML ou uma pasta valida.")
            return
        try:
            matched_files = self.selected_reason_files()
        except Exception as exc:
            messagebox.showerror("Erro", str(exc))
            return

        reason = self.search_text.get().strip() if self.reason_type.get() == "outros" else self.reason_type.get()
        confirmed = messagebox.askyesno(
            "Confirmar busca",
            f"Encontramos {len(matched_files)} arquivo(s) para o motivo '{reason}'.\n\nDeseja prosseguir?",
        )
        if confirmed:
            self.run_task(self.search_reason)

    def search_reason(self) -> Path:
        output_path = self.ensure_output_path(self.output_path.get(), self.select_output_xlsx)
        source, destination = self.validate_paths(self.input_path.get(), output_path)
        reason = self.reason_type.get()
        if reason == "outros":
            reason = self.search_text.get().strip()
            if not reason:
                raise ValueError("Digite o texto que deseja buscar na observacao.")
            generated_path = reference_rows_when_inf_cpl_matches_to_xlsx(source, destination, reason)
            matched_files = self.selected_reason_files()
        else:
            generated_path = fixed_reason_reference_rows_to_xlsx(source, destination, reason)
            matched_files = fixed_reason_xml_files(source, reason)
        danfe_dir = generated_path.parent / f"DANFEs_{safe_folder_name(reason)}"
        generated_danfes, errors = generate_danfes_for_files_safe(matched_files, danfe_dir)
        self.status.set(f"Concluido: planilha, {len(generated_danfes)} DANFEs e {len(errors)} erro(s)")
        return generated_path

def main() -> None:
    App().mainloop()


if __name__ == "__main__":
    main()









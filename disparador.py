import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import json
import os
import pandas as pd
import requests
import random
import string
import uuid
from concurrent.futures import ThreadPoolExecutor
import time

# ===== Config =====
BM_FILE = 'bms.json'
LOG_FILE = 'sent_log.csv'
TEMPLATE_LANG = 'pt_BR'
TOR_PROXY = {
    "http": "socks5h://127.0.0.1:9050",
    "https": "socks5h://127.0.0.1:9050"
}
LOCK = threading.Lock()

def random_namespace():
    u = str(uuid.uuid4())
    p = u.split('-')
    return f"{p[0]}_{p[1]}_{p[2]}_{p[3]}_{p[4]}"

def random_parameter_name(length=6):
    return random.choice(string.ascii_lowercase) + ''.join(random.choices(string.ascii_lowercase + string.digits, k=length-1))

NAMESPACE_VALUE = random_namespace()
PARAM_NAME_VALUE = random_parameter_name()

def carregar_bms():
    if not os.path.exists(BM_FILE):
        return {}
    with open(BM_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def salvar_bms(bms):
    with open(BM_FILE, 'w', encoding='utf-8') as f:
        json.dump(bms, f, indent=4, ensure_ascii=False)

# ===== UI rows =====
class ParamRow(ttk.Frame):
    """Parâmetro do BODY"""
    def __init__(self, master, get_csv_headers_callable, *args, **kwargs):
        super().__init__(master, *args, **kwargs)
        self.get_csv_headers = get_csv_headers_callable
        pad = {'padx': (0, 8), 'pady': 6}

        self.use_random = tk.BooleanVar(value=False)
        self.param_name_entry = ttk.Entry(self)
        self.param_name_entry.grid(row=0, column=0, sticky="ew", **pad)

        self.random_chk = ttk.Checkbutton(
            self, text="Usar PARAM_NAME_VALUE",
            variable=self.use_random, command=self._toggle_param_name
        )
        self.random_chk.grid(row=0, column=1, sticky="w", **pad)

        self.source_type = tk.StringVar(value="Coluna")
        self.source_menu = ttk.Combobox(self, values=["Coluna", "Literal"], state="readonly",
                                        textvariable=self.source_type)
        self.source_menu.grid(row=0, column=2, sticky="w", **pad)
        self.source_menu.bind("<<ComboboxSelected>>", self._switch_source)

        self.col_combo = ttk.Combobox(self, values=self.get_csv_headers(), state="readonly")
        self.col_combo.set("")
        self.col_combo.grid(row=0, column=3, sticky="ew", **pad)

        self.literal_var = tk.StringVar(value="")
        self.literal_entry = ttk.Entry(self, textvariable=self.literal_var)

        self.remove_btn = ttk.Button(self, text="Remover", width=10, command=self._remove)
        self.remove_btn.grid(row=0, column=4, sticky="e", padx=(8, 0), pady=6)

        self.columnconfigure(0, weight=1)
        self.columnconfigure(3, weight=1)

    def _toggle_param_name(self):
        self.param_name_entry.configure(state=("disabled" if self.use_random.get() else "normal"))

    def _switch_source(self, *_):
        if self.source_type.get() == "Coluna":
            self.literal_entry.grid_forget()
            self.col_combo.configure(values=self.get_csv_headers())
            self.col_combo.grid(row=0, column=3, sticky="ew", padx=(0, 8), pady=6)
        else:
            self.col_combo.grid_forget()
            self.literal_entry.grid(row=0, column=3, sticky="ew", padx=(0, 8), pady=6)

    def _remove(self):
        self.destroy()

    def get_mapping(self):
        if self.use_random.get():
            param_name = ("__RANDOM__",)
        else:
            pn = self.param_name_entry.get().strip()
            if not pn:
                return None
            param_name = pn

        if self.source_type.get() == "Coluna":
            col = self.col_combo.get().strip()
            if not col:
                return None
            return {"parameter_name": param_name, "type": "coluna", "value": col}
        else:
            lit = self.literal_var.get()
            return {"parameter_name": param_name, "type": "literal", "value": lit}

class LinkRow(ttk.Frame):
    """Parâmetro de BOTÃO URL dinâmico (CTA)"""
    def __init__(self, master, get_csv_headers_callable, *args, **kwargs):
        super().__init__(master, *args, **kwargs)
        self.get_csv_headers = get_csv_headers_callable
        pad = {'padx': (0, 8), 'pady': 6}

        ttk.Label(self, text="Button index").grid(row=0, column=0, sticky="w", **pad)
        self.index_var = tk.StringVar(value="0")
        self.index_combo = ttk.Combobox(self, values=["0","1","2","3","4","5","6","7","8","9"], width=4,
                                        state="readonly", textvariable=self.index_var)
        self.index_combo.grid(row=0, column=1, sticky="w", **pad)

        self.source_type = tk.StringVar(value="Coluna")
        self.source_menu = ttk.Combobox(self, values=["Coluna", "Literal"], state="readonly",
                                        textvariable=self.source_type)
        self.source_menu.grid(row=0, column=2, sticky="w", **pad)
        self.source_menu.bind("<<ComboboxSelected>>", self._switch_source)

        self.col_combo = ttk.Combobox(self, values=self.get_csv_headers(), state="readonly", width=28)
        self.col_combo.set("")
        self.col_combo.grid(row=0, column=3, sticky="ew", **pad)

        self.literal_var = tk.StringVar(value="")
        self.literal_entry = ttk.Entry(self, textvariable=self.literal_var)

        self.remove_btn = ttk.Button(self, text="Remover", width=10, command=self._remove)
        self.remove_btn.grid(row=0, column=4, sticky="e", padx=(8, 0), pady=6)

        self.columnconfigure(3, weight=1)

    def _switch_source(self, *_):
        if self.source_type.get() == "Coluna":
            self.literal_entry.grid_forget()
            self.col_combo.configure(values=self.get_csv_headers())
            self.col_combo.grid(row=0, column=3, sticky="ew", padx=(0, 8), pady=6)
        else:
            self.col_combo.grid_forget()
            self.literal_entry.grid(row=0, column=3, sticky="ew", padx=(0, 8), pady=6)

    def _remove(self):
        self.destroy()

    def get_link_mapping(self):
        idx = self.index_var.get().strip()
        if not idx.isdigit():
            return None
        if self.source_type.get() == "Coluna":
            col = self.col_combo.get().strip()
            if not col:
                return None
            return {"index": int(idx), "type": "coluna", "value": col}
        else:
            return {"index": int(idx), "type": "literal", "value": self.literal_var.get()}

# ===== Build payload pieces =====
def build_body_parameters(rows, lead):
    params = []
    for row in rows:
        m = row.get_mapping()
        if not m:
            continue
        parameter_name = PARAM_NAME_VALUE if isinstance(m["parameter_name"], tuple) else m["parameter_name"]
        text_value = str(lead.get(m["value"], "")) if m["type"] == "coluna" else str(m["value"])
        params.append({"type": "text", "parameter_name": parameter_name, "text": text_value})
    return params

def build_button_components(link_rows, lead):
    """Gera components de botão URL dinâmico (cada item é um component)."""
    components = []
    for lr in link_rows:
        m = lr.get_link_mapping()
        if not m:
            continue
        text_value = str(lead.get(m["value"], "")) if m["type"] == "coluna" else str(m["value"])
        components.append({
            "type": "button",
            "sub_type": "url",
            "index": str(m["index"]),
            "parameters": [{"type": "text", "text": text_value}]
        })
    return components

# ===== Envio =====
def enviar_template(lead, phone_number_id, token, body_rows, link_rows,
                    log_callback=None, log_enabled=True):
    api_url = f"https://graph.facebook.com/v23.0/{phone_number_id}/messages"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
    template_name = str(lead.get('template_name', '')).strip()

    body_params = build_body_parameters(body_rows, lead)
    button_components = build_button_components(link_rows, lead)

    components = []
    if body_params:
        components.append({"type": "body", "parameters": body_params})
    # anexar os components de botão (URL dinâmico)
    components.extend(button_components)

    payload = {
        "type": "template",
        "messaging_product": "whatsapp",
        "template": {
            #"namespace": NAMESPACE_VALUE,
            "name": template_name,
            "language": {"code": TEMPLATE_LANG},
            "components": components
        },
        "to": str(lead.get('telefone', ''))
    }

    try:
        r = requests.post(api_url, headers=headers, json=payload, proxies=TOR_PROXY, timeout=30)
        msg = f"{lead.get('telefone','')}: {r.status_code} | {r.text[:140]}"
        if log_callback:
            log_callback(msg)
        if r.status_code == 200 and log_enabled:
            with LOCK:
                with open(LOG_FILE, "a", encoding='utf-8') as f:
                    f.write(f"{lead.get('telefone','')}\n")
    except Exception as e:
        if log_callback:
            log_callback(f"Erro: {e}")

def modo_envio(bm_obj, csv_df, body_rows, link_rows, random_mode=False, log_callback=None):
    if not bm_obj:
        if log_callback: log_callback("❌ Nenhuma BM selecionada.")
        return

    phone_number_id = bm_obj['phone_number_id']
    token = bm_obj['token']
    templates = bm_obj['templates'] or []

    if not os.path.exists(LOG_FILE):
        open(LOG_FILE, "w", encoding='utf-8').close()

    with open(LOG_FILE, "r", encoding='utf-8') as f:
        enviados = set(line.strip() for line in f)

    if 'telefone' not in csv_df.columns:
        if log_callback: log_callback("❌ CSV precisa da coluna 'telefone'.")
        return

    leads_df = csv_df.copy()
    leads_df['telefone'] = leads_df['telefone'].astype(str)
    leads_df = leads_df[~leads_df['telefone'].isin(enviados)].reset_index(drop=True)

    if random_mode:
        leads_df = leads_df.sample(frac=1).reset_index(drop=True)

    if not templates:
        if log_callback: log_callback("❌ Nenhum template cadastrado.")
        return

    num_templates = len(templates)
    total = len(leads_df)
    leads_df['template_name'] = [templates[i % num_templates] for i in range(total)]
    if log_callback:
        log_callback(f"📤 Enviando para {total} leads…")

    with ThreadPoolExecutor(max_workers=1) as executor:
        for _, lead in leads_df.iterrows():
            executor.submit(
                enviar_template, lead, phone_number_id, token, body_rows, link_rows,
                log_callback, not random_mode
            )
            time.sleep(1)

# ===== Scrollable =====
class ScrollableFrame(ttk.Frame):
    def __init__(self, master, height=300, *args, **kwargs):
        super().__init__(master, *args, **kwargs)
        self.canvas = tk.Canvas(self, highlightthickness=0, bd=0)
        self.vscroll = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = ttk.Frame(self.canvas)

        self.inner.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self.vscroll.set, height=height)

        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.vscroll.grid(row=0, column=1, sticky="ns")
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)

    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")

# ===== App =====
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("WhatsApp Sender (Tkinter)")
        self.geometry("1180x760")
        self.minsize(980, 640)
        self._setup_style_dark()

        self.bms = carregar_bms()
        self.selected_bm_name = None
        self.selected_bm_obj = None
        self.csv_df = pd.DataFrame()

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # Sidebar
        self.sidebar = ttk.Frame(self, style="Card.TFrame", padding=14)
        self.sidebar.grid(row=0, column=0, rowspan=3, sticky="nsw")

        ttk.Label(self.sidebar, text="⚙️ Configurações", style="Title.TLabel").pack(anchor="w", pady=(0, 10))
        ttk.Label(self.sidebar, text="Business Manager", style="Label.TLabel").pack(anchor="w", pady=(6, 2))
        self.bm_menu_var = tk.StringVar(value="")
        self.bm_menu = ttk.Combobox(self.sidebar, values=list(self.bms.keys()),
                                    textvariable=self.bm_menu_var, state="readonly")
        self.bm_menu.pack(fill="x", pady=2)
        self.bm_menu.bind("<<ComboboxSelected>>", self._select_bm)

        ttk.Button(self.sidebar, text="Cadastrar BM", style="Accent.TButton",
                   command=self._cadastrar_bm).pack(fill="x", pady=(8, 6))
        ttk.Button(self.sidebar, text="Recarregar BMs",
                   command=self._refresh_bms).pack(fill="x", pady=(0, 12))

        ttk.Label(self.sidebar, text="Arquivo CSV", style="Label.TLabel").pack(anchor="w", pady=(6, 2))
        ttk.Button(self.sidebar, text="Selecionar CSV",
                   command=self._pick_csv).pack(fill="x", pady=2)

        self.csv_label_var = tk.StringVar(value="Nenhum arquivo selecionado")
        ttk.Label(self.sidebar, textvariable=self.csv_label_var, style="Hint.TLabel",
                  wraplength=240, justify="left").pack(anchor="w", pady=(4, 12))

        ttk.Button(self.sidebar, text="Enviar (Normal)",
                   command=lambda: self._start_envio(False)).pack(fill="x", pady=(4, 6))
        ttk.Button(self.sidebar, text="Enviar (Aleatório)",
                   command=lambda: self._start_envio(True)).pack(fill="x", pady=(0, 10))

        # ===== Painel parâmetros BODY =====
        self.body_card = ttk.Frame(self, padding=10, style="Card.TFrame")
        self.body_card.grid(row=1, column=1, sticky="nsew", padx=10, pady=(0, 8))
        self.body_card.grid_columnconfigure(0, weight=1)

        header = ttk.Frame(self.body_card, style="Card.TFrame")
        header.grid(row=0, column=0, sticky="ew")
        ttk.Label(header, text="Parâmetros do Template (BODY)", style="Subtitle.TLabel").pack(side="left")
        ttk.Button(header, text="Exemplo rápido", command=self._fill_example_rows).pack(side="right")

        self.rows_body = ScrollableFrame(self.body_card, height=220)
        self.rows_body.grid(row=1, column=0, sticky="nsew", pady=(10, 10))

        actions = ttk.Frame(self.body_card, style="Card.TFrame")
        actions.grid(row=2, column=0, sticky="ew")
        ttk.Button(actions, text="Adicionar parâmetro", command=self._add_param_row).pack(side="left")

        # ===== Painel Links Dinâmicos =====
        self.links_card = ttk.Frame(self, padding=10, style="Card.TFrame")
        self.links_card.grid(row=2, column=1, sticky="nsew", padx=10, pady=(0, 10))
        self.links_card.grid_columnconfigure(0, weight=1)

        header2 = ttk.Frame(self.links_card, style="Card.TFrame")
        header2.grid(row=0, column=0, sticky="ew")
        ttk.Label(header2, text="Links dinâmicos (botões URL)", style="Subtitle.TLabel").pack(side="left")
        ttk.Button(header2, text="Exemplo de link", command=self._fill_example_link).pack(side="right")

        self.rows_links = ScrollableFrame(self.links_card, height=160)
        self.rows_links.grid(row=1, column=0, sticky="nsew", pady=(10, 10))

        actions2 = ttk.Frame(self.links_card, style="Card.TFrame")
        actions2.grid(row=2, column=0, sticky="ew")
        ttk.Button(actions2, text="Adicionar link dinâmico", command=self._add_link_row).pack(side="left")

        # ===== Log =====
        self.log_card = ttk.Frame(self, padding=10, style="Card.TFrame")
        self.log_card.grid(row=3, column=0, columnspan=2, sticky="nsew", padx=10, pady=(0, 10))
        self.log_text = tk.Text(self.log_card, height=10, wrap="word", bg="#0b1220",
                                fg="#e6e6e6", insertbackground="#e6e6e6", relief="flat")
        self.log_text.pack(fill="both", expand=True)
        self._log("✅ Interface iniciada.")
        self._add_param_row()

    # ===== Estilo dark =====
    def _setup_style_dark(self):
        self.style = ttk.Style()
        try: self.style.theme_use("clam")
        except tk.TclError: pass

        bg="#0f172a"; card="#111827"; panel="#0b1220"; fg="#e5e7eb"; fg_muted="#9ca3af"
        primary="#3b82f6"; primary_hover="#2563eb"; border="#1f2937"
        self.configure(bg=bg)

        self.style.configure("TFrame", background=bg)
        self.style.configure("Card.TFrame", background=card, borderwidth=1, relief="solid")
        self.style.configure("TLabel", background=card, foreground=fg)
        self.style.configure("Label.TLabel", background=card, foreground=fg)
        self.style.configure("Hint.TLabel", background=card, foreground=fg_muted)
        self.style.configure("Title.TLabel", background=card, foreground=fg, font=("Segoe UI",16,"bold"))
        self.style.configure("Subtitle.TLabel", background=card, foreground=fg, font=("Segoe UI",12,"bold"))
        self.style.configure("TButton", background=card, foreground=fg, borderwidth=0, padding=8)
        self.style.map("TButton", background=[("active", border)], foreground=[("disabled", fg_muted)])
        self.style.configure("Accent.TButton", background=primary, foreground="#fff", padding=8)
        self.style.map("Accent.TButton", background=[("active", primary_hover)])
        field = dict(fieldbackground=panel, background=panel, foreground=fg)
        self.style.configure("TCombobox", **field, selectforeground=fg, selectbackground=panel, padding=6)
        self.style.configure("TEntry", **field, padding=6)
        self.style.configure("TCheckbutton", background=card, foreground=fg)

    # ===== Helpers =====
    def _threadsafe_log(self, msg):
        self.after(0, self._log, msg)

    def _log(self, msg):
        self.log_text.insert("end", msg + "\n")
        self.log_text.see("end")

    def _get_csv_headers(self):
        if self.csv_df is None or self.csv_df.empty:
            return []
        return list(map(str, self.csv_df.columns))

    def _add_param_row(self):
        row = ParamRow(self.rows_body.inner, get_csv_headers_callable=self._get_csv_headers)
        row.grid(sticky="ew", padx=6, pady=4)
        return row

    def _add_link_row(self):
        row = LinkRow(self.rows_links.inner, get_csv_headers_callable=self._get_csv_headers)
        row.grid(sticky="ew", padx=6, pady=4)
        return row

    def _fill_example_rows(self):
        for c in list(self.rows_body.inner.winfo_children()):
            if isinstance(c, ParamRow): c.destroy()
        r1 = self._add_param_row()
        r1.use_random.set(True); r1._toggle_param_name()
        r1.source_type.set("Coluna"); r1._switch_source(); r1.col_combo.set("nome")
        r2 = self._add_param_row()
        r2.param_name_entry.insert(0, "serie")
        r2.source_type.set("Coluna"); r2._switch_source(); r2.col_combo.set("telefone")
        r3 = self._add_param_row()
        r3.param_name_entry.insert(0, "indicacao")
        r3.source_type.set("Literal"); r3._switch_source(); r3.literal_var.set("serie")
        self._log("Exemplo (BODY) preenchido.")

    def _fill_example_link(self):
        for c in list(self.rows_links.inner.winfo_children()):
            if isinstance(c, LinkRow): c.destroy()
        lr = self._add_link_row()
        lr.index_var.set("0")
        lr.source_type.set("Coluna"); lr._switch_source(); lr.col_combo.set("codigo")  # coluna exemplo
        self._log("Exemplo (Link dinâmico) preenchido. Obs: o template deve ter URL dinâmica {{1}} no botão 0.")

    # ===== Ações =====
    def _select_bm(self, *_):
        name = self.bm_menu_var.get()
        self.selected_bm_name = name
        self.selected_bm_obj = self.bms.get(name)
        self._log(f"BM selecionada: {name}")

    def _refresh_bms(self):
        self.bms = carregar_bms()
        self.bm_menu.configure(values=list(self.bms.keys()))
        self._log("Lista de BMs atualizada.")

    def _cadastrar_bm(self):
        top = tk.Toplevel(self); top.title("Cadastrar BM"); top.geometry("420x380"); top.configure(bg="#111827")
        container = ttk.Frame(top, padding=14, style="Card.TFrame"); container.pack(fill="both", expand=True)
        def row(lbl):
            f=ttk.Frame(container, style="Card.TFrame"); f.pack(fill="x", pady=6)
            ttk.Label(f, text=lbl, style="Label.TLabel", width=18).pack(side="left")
            e=ttk.Entry(f); e.pack(side="left", fill="x", expand=True); return e
        nome=row("Nome:"); phone=row("Phone Number ID:"); token=row("Token:"); token.configure(show="*"); temps=row("Templates (vírgula):")
        def salvar():
            n=nome.get().strip(); p=phone.get().strip(); t=token.get().strip(); ts=[x.strip() for x in temps.get().split(",") if x.strip()]
            if not n or not p or not t or not ts: messagebox.showwarning("Atenção","Preencha todos os campos."); return
            bms=carregar_bms(); bms[n]={"phone_number_id":p,"token":t,"templates":ts}; salvar_bms(bms)
            self._refresh_bms(); self._log(f"BM {n} salva."); top.destroy()
        ttk.Button(container, text="Salvar", style="Accent.TButton", command=salvar).pack(pady=12, fill="x")

    def _pick_csv(self):
        path = filedialog.askopenfilename(title="Selecionar CSV", filetypes=[("CSV files", "*.csv")])
        if not path: return
        try:
            df = pd.read_csv(path)
            self.csv_df = df
            self.csv_label_var.set(os.path.basename(path))
            self._log(f"CSV carregado: {path}")
        except Exception as e:
            self._log(f"Erro: {e}")

    def _start_envio(self, random_mode):
        if not self.selected_bm_obj:
            self._log("Selecione uma BM."); return
        if self.csv_df is None or self.csv_df.empty:
            self._log("Selecione um CSV válido."); return

        body_rows = [w for w in self.rows_body.inner.winfo_children() if isinstance(w, ParamRow)]
        link_rows = [w for w in self.rows_links.inner.winfo_children() if isinstance(w, LinkRow)]
        if not body_rows and not link_rows:
            self._log("Adicione pelo menos um parâmetro de BODY ou um link dinâmico."); return

        t = threading.Thread(target=modo_envio,
                             args=(self.selected_bm_obj, self.csv_df, body_rows, link_rows, random_mode, self._threadsafe_log),
                             daemon=True)
        t.start()

if __name__ == "__main__":
    app = App()
    app.mainloop()

import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog
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

class ParamRow(ctk.CTkFrame):
    def __init__(self, master, get_csv_headers_callable, *args, **kwargs):
        super().__init__(master, *args, **kwargs)
        self.get_csv_headers = get_csv_headers_callable
        self.use_random = tk.BooleanVar(value=False)
        self.param_name_entry = ctk.CTkEntry(self, placeholder_text="parameter_name")
        self.param_name_entry.grid(row=0, column=0, padx=(0,8), pady=6, sticky="ew")
        self.random_chk = ctk.CTkCheckBox(self, text="Usar PARAM_NAME_VALUE", variable=self.use_random, command=self._toggle_param_name)
        self.random_chk.grid(row=0, column=1, padx=(0,8), pady=6, sticky="w")
        self.source_type = tk.StringVar(value="Coluna")
        self.source_menu = ctk.CTkOptionMenu(self, values=["Coluna", "Literal"], command=self._switch_source)
        self.source_menu.grid(row=0, column=2, padx=(0,8), pady=6, sticky="w")
        self.col_combo = ctk.CTkComboBox(self, values=self.get_csv_headers(), width=220)
        self.col_combo.set("")
        self.col_combo.grid(row=0, column=3, padx=(0,8), pady=6, sticky="ew")
        self.literal_entry = ctk.CTkEntry(self, placeholder_text='texto fixo', width=220)
        self.literal_entry.grid_forget()
        self.remove_btn = ctk.CTkButton(self, text="Remover", width=80, command=self._remove)
        self.remove_btn.grid(row=0, column=4, padx=(8,0), pady=6)
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(3, weight=1)

    def _toggle_param_name(self):
        if self.use_random.get():
            self.param_name_entry.configure(state="disabled")
        else:
            self.param_name_entry.configure(state="normal")

    def _switch_source(self, *_):
        if self.source_type.get() == "Coluna":
            self.literal_entry.grid_forget()
            self.col_combo.configure(values=self.get_csv_headers())
            self.col_combo.grid(row=0, column=3, padx=(0,8), pady=6, sticky="ew")
        else:
            self.col_combo.grid_forget()
            self.literal_entry.grid(row=0, column=3, padx=(0,8), pady=6, sticky="ew")

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
        stype = self.source_type.get()
        if stype == "Coluna":
            col = self.col_combo.get().strip()
            if not col:
                return None
            return {"parameter_name": param_name, "type": "coluna", "value": col}
        else:
            lit = self.literal_entry.get()
            return {"parameter_name": param_name, "type": "literal", "value": lit}

def build_parameters_from_rows(rows, lead):
    params = []
    for row in rows:
        m = row.get_mapping()
        if not m:
            continue
        if isinstance(m["parameter_name"], tuple):
            parameter_name = PARAM_NAME_VALUE
        else:
            parameter_name = m["parameter_name"]
        if m["type"] == "coluna":
            text_value = str(lead.get(m["value"], ""))
        else:
            text_value = str(m["value"])
        params.append({"type": "text", "parameter_name": parameter_name, "text": text_value})
    return params

def enviar_template(lead, phone_number_id, token, params_rows, log_callback=None, log_enabled=True):
    api_url = f"https://graph.facebook.com/v23.0/{phone_number_id}/messages"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
    template_name = str(lead.get('template_name', '')).strip()
    body_params = build_parameters_from_rows(params_rows, lead)
    payload = {
        "type": "template",
        "messaging_product": "whatsapp",
        "template": {
            "namespace": NAMESPACE_VALUE,
            "name": template_name,
            "language": {"code": TEMPLATE_LANG},
            "components": [{"type": "body", "parameters": body_params}]
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

def modo_envio(bm_obj, csv_df, params_rows, random_mode=False, log_callback=None):
    if not bm_obj:
        if log_callback:
            log_callback("❌ Nenhuma BM selecionada.")
        return
    phone_number_id = bm_obj['phone_number_id']
    token = bm_obj['token']
    templates = bm_obj['templates'] or []
    if not os.path.exists(LOG_FILE):
        open(LOG_FILE, "w", encoding='utf-8').close()
    with open(LOG_FILE, "r", encoding='utf-8') as f:
        enviados = set(line.strip() for line in f)
    if 'telefone' not in csv_df.columns:
        log_callback("❌ CSV precisa da coluna 'telefone'.")
        return
    leads_df = csv_df.copy()
    leads_df['telefone'] = leads_df['telefone'].astype(str)
    leads_df = leads_df[~leads_df['telefone'].isin(enviados)].reset_index(drop=True)
    if random_mode:
        leads_df = leads_df.sample(frac=1).reset_index(drop=True)
    if not templates:
        log_callback("❌ Nenhum template cadastrado.")
        return
    num_templates = len(templates)
    total = len(leads_df)
    leads_df['template_name'] = [templates[i % num_templates] for i in range(total)]
    log_callback(f"📤 Enviando para {total} leads…")
    with ThreadPoolExecutor(max_workers=1) as executor:
        for _, lead in leads_df.iterrows():
            executor.submit(enviar_template, lead, phone_number_id, token, params_rows, log_callback, not random_mode)
            time.sleep(1)

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("WhatsApp Sender - Modo Escuro")
        self.geometry("1100x690")
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")
        self.bms = carregar_bms()
        self.selected_bm_name = None
        self.selected_bm_obj = None
        self.csv_path = None
        self.csv_df = pd.DataFrame()
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self.sidebar = ctk.CTkFrame(self, width=260)
        self.sidebar.grid(row=0, column=0, rowspan=2, sticky="nsw")
        ctk.CTkLabel(self.sidebar, text="⚙️ Configurações", font=("Segoe UI", 17, "bold")).pack(padx=14, pady=(14,8), anchor="w")
        ctk.CTkLabel(self.sidebar, text="Business Manager").pack(padx=14, pady=(6,2), anchor="w")
        self.bm_menu = ctk.CTkOptionMenu(self.sidebar, values=list(self.bms.keys()), command=self._select_bm)
        self.bm_menu.pack(padx=14, pady=6, fill="x")
        ctk.CTkButton(self.sidebar, text="Cadastrar BM", command=self._cadastrar_bm).pack(padx=14, pady=(4,12), fill="x")
        ctk.CTkButton(self.sidebar, text="Recarregar BMs", command=self._refresh_bms).pack(padx=14, pady=(0,18), fill="x")
        ctk.CTkLabel(self.sidebar, text="Arquivo CSV").pack(padx=14, pady=(0,2), anchor="w")
        ctk.CTkButton(self.sidebar, text="Selecionar CSV", command=self._pick_csv).pack(padx=14, pady=6, fill="x")
        self.csv_label = ctk.CTkLabel(self.sidebar, text="Nenhum arquivo selecionado", wraplength=220)
        self.csv_label.pack(padx=14, pady=(2,10), anchor="w")
        ctk.CTkButton(self.sidebar, text="Enviar (Normal)", command=lambda: self._start_envio(False)).pack(padx=14, pady=(8,6), fill="x")
        ctk.CTkButton(self.sidebar, text="Enviar (Aleatório)", command=lambda: self._start_envio(True)).pack(padx=14, pady=(0,14), fill="x")
        self.param_frame = ctk.CTkFrame(self)
        self.param_frame.grid(row=1, column=1, sticky="nsew", padx=10, pady=(0,10))
        self.param_frame.grid_columnconfigure(0, weight=1)
        self.rows_container = ctk.CTkScrollableFrame(self.param_frame, height=280)
        self.rows_container.grid(row=1, column=0, sticky="nsew", padx=10, pady=(10,10))
        self.add_row_btn = ctk.CTkButton(self.param_frame, text="Adicionar parâmetro", command=self._add_param_row)
        self.add_row_btn.grid(row=2, column=0, sticky="w", padx=10, pady=(0,10))
        self.example_btn = ctk.CTkButton(self.param_frame, text="Exemplo rápido", command=self._fill_example_rows)
        self.example_btn.grid(row=2, column=0, sticky="e", padx=10, pady=(0,10))
        self.log_box = ctk.CTkTextbox(self, wrap="word", height=180)
        self.log_box.grid(row=2, column=0, columnspan=2, sticky="nsew", padx=10, pady=(0,10))
        self._log("✅ Interface iniciada.")
        self._add_param_row()

    def _select_bm(self, name):
        self.selected_bm_name = name
        self.selected_bm_obj = self.bms.get(name)
        self._log(f"BM selecionada: {name}")

    def _refresh_bms(self):
        self.bms = carregar_bms()
        self.bm_menu.configure(values=list(self.bms.keys()))
        self._log("Lista de BMs atualizada.")

    def _cadastrar_bm(self):
        win = ctk.CTkToplevel(self)
        win.title("Cadastrar BM")
        win.geometry("400x350")
        ctk.CTkLabel(win, text="Nome:").pack(pady=5)
        nome = ctk.CTkEntry(win)
        nome.pack(pady=5)
        ctk.CTkLabel(win, text="Phone Number ID:").pack(pady=5)
        phone = ctk.CTkEntry(win)
        phone.pack(pady=5)
        ctk.CTkLabel(win, text="Token:").pack(pady=5)
        token = ctk.CTkEntry(win, show="*")
        token.pack(pady=5)
        ctk.CTkLabel(win, text="Templates (vírgula):").pack(pady=5)
        temps = ctk.CTkEntry(win)
        temps.pack(pady=5)
        def salvar():
            bms = carregar_bms()
            bms[nome.get()] = {"phone_number_id": phone.get(), "token": token.get(), "templates": [t.strip() for t in temps.get().split(",")]}
            salvar_bms(bms)
            self._refresh_bms()
            win.destroy()
            self._log(f"BM {nome.get()} salva.")
        ctk.CTkButton(win, text="Salvar", command=salvar).pack(pady=15)

    def _pick_csv(self):
        path = filedialog.askopenfilename(title="Selecionar CSV", filetypes=[("CSV files", "*.csv")])
        if not path:
            return
        try:
            df = pd.read_csv(path)
            self.csv_df = df
            self.csv_label.configure(text=os.path.basename(path))
            self._log(f"CSV carregado: {path}")
        except Exception as e:
            self._log(f"Erro: {e}")

    def _get_csv_headers(self):
        if self.csv_df is None or self.csv_df.empty:
            return []
        return list(map(str, self.csv_df.columns))

    def _add_param_row(self):
        row = ParamRow(self.rows_container, get_csv_headers_callable=self._get_csv_headers)
        row.grid(sticky="ew", padx=6, pady=4)
        return row

    def _fill_example_rows(self):
        for c in list(self.rows_container.winfo_children()):
            if isinstance(c, ParamRow):
                c.destroy()
        r1 = self._add_param_row()
        r1.use_random.set(True)
        r1._toggle_param_name()
        r1.source_menu.set("Coluna")
        r1._switch_source()
        r1.col_combo.set("nome")
        r2 = self._add_param_row()
        r2.param_name_entry.insert(0, "serie")
        r2.source_menu.set("Coluna")
        r2._switch_source()
        r2.col_combo.set("telefone")
        r3 = self._add_param_row()
        r3.param_name_entry.insert(0, "indicacao")
        r3.source_menu.set("Literal")
        r3._switch_source()
        r3.literal_entry.insert(0, "serie")
        self._log("Exemplo preenchido.")

    def _start_envio(self, random_mode):
        if not self.selected_bm_obj:
            self._log("Selecione uma BM.")
            return
        if self.csv_df is None or self.csv_df.empty:
            self._log("Selecione um CSV válido.")
            return
        rows = [w for w in self.rows_container.winfo_children() if isinstance(w, ParamRow)]
        if not rows:
            self._log("Adicione ao menos um parâmetro.")
            return
        threading.Thread(target=modo_envio, args=(self.selected_bm_obj, self.csv_df, rows, random_mode, self._log), daemon=True).start()

    def _log(self, msg):
        self.log_box.insert("end", msg + "\n")
        self.log_box.see("end")

if __name__ == "__main__":
    app = App()
    app.mainloop()

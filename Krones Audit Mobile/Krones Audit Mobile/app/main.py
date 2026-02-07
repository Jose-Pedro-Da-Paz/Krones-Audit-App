# app/main.py
from kivymd.app import MDApp
from kivy.lang import Builder
from kivy.metrics import dp
from kivy.properties import DictProperty, StringProperty, ObjectProperty
from kivy.uix.filechooser import FileChooserIconView  # desktop popup
from kivymd.uix.filemanager import MDFileManager      # Android (opção B)
from kivy.core.window import Window
from kivy.uix.scrollview import ScrollView
from kivy.factory import Factory
from kivy.uix.popup import Popup
from kivy.utils import platform
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.filechooser import FileChooserIconView

import os, json

from kivymd.uix.tab import MDTabsBase
from kivymd.uix.boxlayout import MDBoxLayout, BoxLayout
from kivymd.uix.list import IconRightWidget
from kivymd.uix.selectioncontrol import MDCheckbox
from kivymd.uix.label import MDLabel
from kivy.uix.floatlayout import FloatLayout
from kivymd.uix.card import MDCard
from kivymd.uix.dialog import MDDialog
from kivymd.uix.textfield import MDTextField
from kivymd.uix.button import MDFlatButton, MDRaisedButton  # KivyMD 1.x
from kivy.uix.widget import Widget
from kivymd.uix.snackbar import MDSnackbar

from pathlib import Path

from .model import Schema, Topic
from .i18n import get_title
from .calculator import final_score, topic_score
from .storage import build_result
# Em dev desktop (ignorado no Android)
try:
    Window.size = (500, 800)
except Exception:
    pass


class TopicTab(MDBoxLayout, MDTabsBase):
    """Conteúdo de uma aba de Tópico para KivyMD 1.x"""
    topic: Topic
    lang: str

# ---- Dialogs para Desktop (Salvar Como...) ----
class SaveDialog(FloatLayout):
    save = ObjectProperty(None)
    cancel = ObjectProperty(None)
    text_input = ObjectProperty(None)
    path = StringProperty(os.path.expanduser("~"))

    def _ensure_json_name(name: str) -> str:
        name = (name or "").strip()
        return name if name.lower().endswith(".json") else f"{name}.json"
    
    
    
class AuditoriaApp(MDApp):
    lang = StringProperty("pt-BR")
    schema: Schema = ObjectProperty(None, rebind=True)

    # Respostas e comentários do usuário
    answers = DictProperty()   # { "1.1.1": "75", ... , "1.1.2": "N.A." }
    comments = DictProperty()  # { "1.1.1": "observação", ... }

    dialog = None


    def build(self):
        kv_path = Path(__file__).with_name("ui") / "screens.kv"
        root = Builder.load_file(str(kv_path))
        if root is None:
            root = Factory.RootScreen()

        self.load_questions()
        self.build_tabs(root.ids.tabs)

        # Inicializa o rótulo do resultado SEM usar self.root (ainda é None aqui)
        final = final_score(self.schema.topics, self.answers)
        root.ids.final_score_label.text = (
            f"Resultado: {round(final*100,1)}%" if final is not None else "Resultado: —"
        )

        return root

    def on_start(self):
        # Agora self.root já existe; aqui é seguro tocar na árvore de widgets
        self._request_android_permissions()
        self.update_scores_ui()

    def _request_android_permissions(self):
        if platform != "android":
            return
        try:
            from android.permissions import Permission, request_permissions

            request_permissions([
                Permission.READ_EXTERNAL_STORAGE,
                Permission.WRITE_EXTERNAL_STORAGE,
            ])
        except Exception as exc:
            print(f"[PERMISSION WARNING] Não foi possível solicitar permissões: {exc}")


    def build_tabs(self, tabs):
        # --- Remova as abas existentes (1.x não tem clear_tabs) ---
        try:
            for t in list(tabs.get_tab_list()):
                tabs.remove_widget(t)
        except Exception:
            from kivymd.uix.tab import MDTabsBase
            for child in list(tabs.children):
                if isinstance(child, MDTabsBase):
                    tabs.remove_widget(child)

        # --- Crie as novas abas ---
        for topic in self.schema.topics:
            tab = TopicTab()
            tab.title = get_title(topic.title, self.lang) or f"Tópico {topic.id}"
            tab.topic = topic
            tab.lang = self.lang
            tab.orientation = "vertical"

            # Card com a média do tópico (como você já tinha)
            score_card = MDCard(orientation="horizontal",
                                padding=dp(8), size_hint_y=None, height=dp(48))
            score_label = MDLabel(id=f"score_{topic.id}",
                                text="Média do tópico: —",
                                halign="left",
                                theme_text_color="Primary",
                                font_style="Subtitle2")
            score_card.add_widget(score_label)
            tab.add_widget(score_card)

            # ---------- Scroll + PILHA (substitui MDList) ----------
            sc = ScrollView(do_scroll_x=False, do_scroll_y=True)

            pile = MDBoxLayout(orientation="vertical",
                            spacing=dp(8),
                            padding=(dp(8), dp(4), dp(8), dp(12)))
            pile.size_hint_y = None
            pile.bind(minimum_height=pile.setter("height"))

            sc.add_widget(pile)

            # ---------- Cabeçalhos de GRUPO + Perguntas ----------
            for group in topic.groups:
                group_title = get_title(group.title, self.lang) or f"Grupo {group.id}"

                header = MDLabel(text=f"[b]{group_title}[/b]",
                                markup=True,
                                size_hint_y=None)
                # quebra de linha automática
                def _sync_header_width(inst, width):
                    inst.text_size = (width - dp(16), None)
                header.bind(
                    width=_sync_header_width,
                    texture_size=lambda inst, val: setattr(inst, "height", val[1] + dp(6)),
                )
                pile.add_widget(header)

                for q in group.questions:
                    pile.add_widget(self._build_question_row(q))

            tab.add_widget(sc)
            tabs.add_widget(tab)

        # (opcional) log rápido para checagem
        try:
            total_groups = sum(len(t.groups) for t in self.schema.topics)
            total_questions = sum(len(g.questions) for t in self.schema.topics for g in t.groups)
            print(f"[DEBUG] tópicos={len(self.schema.topics)} grupos={total_groups} perguntas={total_questions}")
        except Exception:
            pass


    def load_questions(self):
        """
        Carrega o schema (tópicos/grupos/perguntas) a partir de app/data/questions.json
        e garante que o idioma atual é suportado.
        """
        from pathlib import Path
        from .model import load_schema  # garante import local aqui também

        data_path = Path(__file__).with_name("data") / "questions.json"
        if not data_path.exists():
            # Evita crash e informa o usuário no app
            try:
                from kivymd.uix.snackbar import Snackbar
                Snackbar(text=f"Arquivo não encontrado: {data_path.name}", duration=3).open()
            except Exception:
                pass
            # Cria um Schema vazio mínimo para não quebrar build_tabs
            self.schema = type("Schema", (), {"languages": ["pt-BR"], "topics": []})()
            return

        self.schema = load_schema(data_path)

        # Se o idioma ativo não existir no arquivo, caia para o primeiro disponível
        if getattr(self, "lang", None) not in self.schema.languages and self.schema.languages:
            self.lang = self.schema.languages[0]
        elif not getattr(self, "lang", None):
            self.lang = "pt-BR"


    def _build_question_row(self, q):
        """Bloco com TÍTULO (quebra de linha) + LINHA DE OPÇÕES + comentário + divisor."""

        # Contêiner vertical com altura adaptativa
        container = MDBoxLayout(
            orientation="vertical",
            padding=(dp(12), dp(8), dp(12), dp(8)),
            spacing=dp(6),
            size_hint_y=None,
        )
        # Faz a altura do container seguir a soma da altura dos filhos
        container.bind(minimum_height=container.setter("height"))

        # ---------- TÍTULO DA PERGUNTA (com quebra de linha) ----------
        title = get_title(q.title, self.lang) or q.id
        title_lbl = MDLabel(
            text=title,
            theme_text_color="Primary",
            halign="left",
            size_hint_y=None,
            # height será vinculada ao texture_size (para caber todo o texto)
        )
        # O texto quebra de linha conforme a largura disponível
        def _sync_text_width(instance, width):
            instance.text_size = (width, None)
        title_lbl.bind(
            texture_size=lambda inst, val: setattr(inst, "height", val[1] + dp(2)),
            width=_sync_text_width
        )
        container.add_widget(title_lbl)

        # ---------- LINHA DE OPÇÕES (100/75/50/25/0/N.A.) ----------
        row = MDBoxLayout(
            orientation="horizontal",
            spacing=dp(8),
            size_hint_y=None,
            height=dp(44),
        )

        def add_choice(value_text, value_payload):
            cb = MDCheckbox(group=q.id, size_hint=(None, None), size=(dp(28), dp(28)))
            current = self.answers.get(q.id)
            if (isinstance(value_payload, int) and current == str(value_payload)) or \
            (isinstance(value_payload, str) and str(current).upper() in {"NA","N.A.","N/A"}):
                cb.active = True

            def on_active(inst, active):
                if not active:
                    return
                self.answers[q.id] = str(value_payload)
                self.update_scores_ui()
            cb.bind(active=on_active)

            lbl = MDLabel(text=value_text, halign="center", size_hint_x=None, width=dp(36))
            col = MDBoxLayout(orientation="horizontal", size_hint_x=None, width=dp(64), spacing=dp(4))
            col.add_widget(cb)
            col.add_widget(lbl)
            row.add_widget(col)

        for v in (100, 75, 50, 25, 0):
            add_choice(str(v), v)
        add_choice("N.A.", "N.A.")

        # Ícone de comentário à direita
        icon = IconRightWidget(icon="comment-text-outline",
                            on_release=lambda w, qid=q.id: self.open_comment_dialog(qid))
        row.add_widget(icon)

        container.add_widget(row)

        spacer = Widget(size_hint=(1,None), height=dp(8))
        container.add_widget(spacer)

        return container

    # ---------- Eventos ----------
    def on_tab_switch(self, *args):
        self.update_scores_ui()

    def toggle_language(self):
        langs = self.schema.languages or ["pt-BR", "es"]
        if self.lang not in langs:
            self.lang = langs[0]
        else:
            idx = langs.index(self.lang)
            self.lang = langs[(idx + 1) % len(langs)]
        tabs = self.root.ids.tabs
        self.build_tabs(tabs)
        self.update_scores_ui()

    def clear_answers(self):
        self.answers = {}
        self.comments = {}
        self.build_tabs(self.root.ids.tabs)
        self.update_scores_ui()

    # ---------- Comentários ----------
    def open_comment_dialog(self, qid: str):
        initial = self.comments.get(qid, "")
        self.dialog = MDDialog(
            title="Comentário",
            type="custom",
            content_cls=MDTextField(text=initial, multiline=True, hint_text="Digite um comentário..."),
            buttons=[
                MDFlatButton(text="Cancelar", on_release=lambda *_: self.dialog.dismiss()),
                MDRaisedButton(text="Salvar", on_release=lambda *_: self._save_comment(qid))
            ],
        )
        self.dialog.open()

    def _save_comment(self, qid: str):
        if not self.dialog:
            return
        textfield = self.dialog.content_cls
        self.comments[qid] = textfield.text or ""
        self.dialog.dismiss()

    # ---------- Cálculo e UI ----------
    def update_scores_ui(self):
        if not self.root:
            return  # evita crash se for chamada antes do build concluir

        # Atualiza o resultado final
        final = final_score(self.schema.topics, self.answers)
        self.root.ids.final_score_label.text = (
            f"Resultado: {round(final*100,1)}%" if final is not None else "Resultado: —"
        )

        # Atualiza os cards de cada aba
        tabs = self.root.ids.tabs
        for tab in tabs.get_tab_list():  # KivyMD 1.x
            if not hasattr(tab, "topic"):
                continue
            ts = topic_score(tab.topic, self.answers)
            txt = "Média do tópico: —" if ts is None else f"Média do tópico: {round(ts*100,1)}%"
            score_card = tab.children[-1] if tab.children else None
            if score_card and hasattr(score_card, "children"):
                lbl = score_card.children[-1] if score_card.children else None
                if isinstance(lbl, MDLabel):
                    lbl.text = txt

    # ---------- Exportação ----------

    def _ask_save_android(self, payload: dict):
        # Dialogo com TextField para o nome do arquivo
        self._name_field = MDTextField(
            text="auditoria.json",
            hint_text="Nome do arquivo",
            helper_text="Será salvo como JSON",
            helper_text_mode="on_focus",
            size_hint_x=1
        )

        self._dlg_android = MDDialog(
            title="Salvar arquivo",
            type="custom",
            content_cls=self._name_field,
            buttons=[
                MDFlatButton(text="Documentos", on_release=lambda *_: self._save_android_documents(payload)),
                MDFlatButton(text="Escolher pasta", on_release=lambda *_: self._save_android_pick_dir(payload)),
                MDFlatButton(text="Cancelar", on_release=lambda *_: self._dlg_android.dismiss()),
            ],
        )
        self._dlg_android.open()
    
    def ask_save_location(self):

        """Monta o payload, salva em JSON e tenta compartilhar. Com logs e tratamento de erro."""
        import traceback
        try:
            # 1) Diagnóstico rápido do estado atual
            total_topics = len(self.schema.topics) if getattr(self, "schema", None) else 0
            total_groups = sum(len(t.groups) for t in self.schema.topics) if total_topics else 0
            total_questions = sum(len(g.questions) for t in self.schema.topics for g in t.groups) if total_groups else 0
            answered = len(self.answers) if hasattr(self, "answers") else 0
            print(f"[EXPORT DEBUG] topics={total_topics} groups={total_groups} questions={total_questions} answered={answered}")
            if total_topics == 0 or total_groups == 0 or total_questions == 0:
                self.show_snackbar("Nada para exportar: schema vazio.")
                return

            # 2) Monta payload
            payload = build_result(
                topics=self.schema.topics,
                answers=dict(self.answers),   # garante dict “puro”
                comments=dict(self.comments), # idem
                language=self.lang,
                auditor=""
            )

            print("[DEBUG] platform =", platform)

            # 3) Salva JSON
            if platform == "android":
                self._ask_save_android(payload)
                
            else:
                self.open_save_dialog_desktop(payload)
                

        except Exception as e:
            tb = traceback.format_exc()
            print("[EXPORT ERROR]", tb)  # log completo no console
            self.show_snackbar(f"Erro ao exportar: {e.__class__.__name__}: {e}")

    def _save_android_documents(self, payload: dict):
        try:
            name = SaveDialog._ensure_json_name(self._name_field.text or "auditoria.json")
            # 1) Salva privado (user_data_dir)
            tmp_full = os.path.join(self.user_data_dir, name)
            import json
            with open(tmp_full, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)

            # 2) Copia p/ STORAGE COMPARTILHADO (Documentos)
            from androidstorage4kivy import SharedStorage
            ss = SharedStorage()
            shared_ref = ss.copy_to_shared(tmp_full, collection="Documents", filepath=None)

            self._dlg_android.dismiss()
            if shared_ref:
                self.show_snack_ok(f"Salvo em Documentos: {name}")
            else:
                self.show_snack_err("Falha ao copiar para Documentos")
        except Exception as e:
            self._dlg_android.dismiss()
            self.show_snack_err(f"Erro: {e}")

    def _save_android_pick_dir(self, payload: dict):
        self._dlg_android.dismiss()
        self._payload_cache = payload
        self._picked_name = SaveDialog._ensure_json_name(self._name_field.text or "auditoria.json")
        self.manager_open = False
        self.file_manager = MDFileManager(
            exit_manager=self._fm_exit_manager,
            select_path=self._fm_select_path_dir
        )
        # Em Android, mostre discos primeiro (quando suportado)
        try:
            self.file_manager.show_disks()
        except Exception:
            # fallback para home
            import os
            self.file_manager.show(os.path.expanduser("~"))
        self.manager_open = True

    def _fm_select_path_dir(self, path: str):
        """Usuário escolheu um diretório; tenta gravar direto (pode falhar em pastas bloqueadas)."""
        self._fm_exit_manager()
        try:
            full = os.path.join(path, self._picked_name)
            import json
            with open(full, "w", encoding="utf-8") as f:
                json.dump(self._payload_cache, f, ensure_ascii=False, indent=2)
            self.show_snack_ok(f"Salvo em: {self._picked_name}")
        except Exception as e:
            # Fallback: Documentos
            self.show_snack_err(f"Sem permissão na pasta; salvando em Documentos... ({e})")
            self._save_android_documents(self._payload_cache)

    def _fm_exit_manager(self, *args):
        try:
            self.file_manager.close()
        except Exception:
            pass
        self.manager_open = False

    def show_snack_ok(self, text: str):
        try:
            MDSnackbar(MDLabel(text=text), y=dp(24),
                    pos_hint={"center_x": .5}, size_hint_x=.9).open()
        except Exception:
            print(text)

    def show_snack_err(self, text: str):
        try:
            MDSnackbar(MDLabel(text=text), y=dp(24),
                    pos_hint={"center_x": .5}, size_hint_x=.9).open()
        except Exception:
            print(f"[ERRO] {text}")



    def open_save_dialog_desktop(self, payload: dict):
        root = BoxLayout(orientation="vertical", spacing=8, padding=8)

        fc = FileChooserIconView(path=os.path.expanduser("~"))
        fc.dirselect = True
        root.add_widget(fc)

        name_row = BoxLayout(size_hint_y=None, height=40, spacing=8)
        name_input = TextInput(text="auditoria.json", multiline=False)
        name_row.add_widget(name_input)
        root.add_widget(name_row)

        btn_row = BoxLayout(size_hint_y=None, height=44, spacing=8)
        btn_cancel = Button(text="Cancelar")
        btn_save   = Button(text="Salvar", bold=True)
        btn_row.add_widget(btn_cancel)
        btn_row.add_widget(btn_save)
        root.add_widget(btn_row)

        popup = Popup(title="Salvar como...", content=root, size_hint=(0.9, 0.9))

        def do_save(*_):
            folder = fc.path if not fc.selection else (
                fc.selection[0] if os.path.isdir(fc.selection[0]) else os.path.dirname(fc.selection[0])
            )
            filename = SaveDialog._ensure_json_name(name_input.text or "auditoria.json")
            full = os.path.join(folder, filename)
            try:
                with open(full, "w", encoding="utf-8") as f:
                    json.dump(payload, f, ensure_ascii=False, indent=2)
                popup.dismiss()
                self.show_snack_ok(f"Salvo em: {os.path.basename(full)}")
            except Exception as e:
                popup.dismiss()
                self.show_snack_err(f"Erro ao salvar: {e}")

        btn_cancel.bind(on_release=lambda *_: popup.dismiss())
        btn_save.bind(on_release=do_save)
        popup.open()

    def _save_desktop_do(self, payload: dict, path: str, filename: str):
        try:
            filename = SaveDialog._ensure_json_name(filename or "auditoria.json")
            full = os.path.join(path, filename)
            # Reusa sua rotina de serialização:
            from .storage import save_json_raw  # crie auxiliar simples se quiser
            # ou simplesmente:
            import json
            with open(full, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            self.dismiss_popup()
            self.show_snack_ok(f"Salvo em: {os.path.basename(full)}")
        except Exception as e:
            self.dismiss_popup()
            self.show_snack_err(f"Erro ao salvar: {e}")

    def dismiss_popup(self, *args):
        try:
            self._popup.dismiss()
        except Exception:
            pass
if __name__ == "__main__":
    AuditoriaApp().run()
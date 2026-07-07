"""
interface.py
"""

import time
import gradio as gr

def erstelle_interface(transkribiere_fn, antworte_fn, verlauf_fn, status_fn):
    with gr.Blocks(title="Lokaler Sprachassistent") as demo:

        gr.Markdown("# 🎙️ Lokaler Sprachassistent")
        gr.Markdown(
            "**Wake Word:** 'Computer'  |  "
            "**STT:** Whisper (large)  |  "
            "**LLM:** Gemma3 (Streaming)  |  "
            "**TTS:** Piper (Echtzeit-Pipeline)"
        )

        gr.Markdown("""
        ### 💬 So funktioniert es:
        1. Sage **'Computer'**
        2. Deine Frage wird transkribiert
        3. Die Antwort wird **wortweise** angezeigt – jedes Wort genau dann,
           wenn es gerade vorgelesen wird.
        """)

        # ─── STATUS ────────────────────────────────────────────────────────
        status_out = gr.Textbox(
            label="Status",
            value="👂 Warte auf Wake Word...",
            lines=1,
            interactive=False,
        )

        # ─── FRAGE & ANTWORT ──────────────────────────────────────────────
        with gr.Row():
            with gr.Column(scale=1):
                frage_out = gr.Textbox(
                    label="📝 Erkannte Frage",
                    lines=3,
                    interactive=False,
                )
            with gr.Column(scale=1):
                antwort_out = gr.Textbox(
                    label="💬 Antwort (synchron zur Stimme)",
                    lines=5,
                    interactive=False,
                )

        # ─── AUDIO ─────────────────────────────────────────────────────────
        audio_out = gr.Audio(
            label="🔊 Aufnahme der Antwort",
            type="filepath",
            interactive=False,
            autoplay=False,
        )

        # ─── TIMER ─────────────────────────────────────────────────────────
        timer = gr.Timer(value=0.3)

        def update_ui():
            status, frage, antwort, wav = status_fn()
            return status, frage, antwort, wav

        timer.tick(update_ui, outputs=[status_out, frage_out, antwort_out, audio_out])

        # ─── VERLAUF ──────────────────────────────────────────────────────
        gr.Markdown("## 📚 Gesprächsverlauf")
        verlauf_tabelle = gr.Dataframe(
            headers=["Zeit", "Frage", "Antwort", "STT(s)", "LLM(s)", "TTS(s)", "Gesamt(s)"],
            label="Alle Gespräche",
            wrap=True,
        )

        def update_table():
            return verlauf_fn()

        timer.tick(update_table, outputs=[verlauf_tabelle])
        demo.load(fn=verlauf_fn, outputs=[verlauf_tabelle])

    return demo
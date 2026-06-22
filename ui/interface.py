"""
interface.py
"""

import gradio as gr


def erstelle_interface(transkribiere_fn, antworte_fn, verlauf_fn):
    with gr.Blocks(title="Lokaler Sprachassistent") as demo:

        gr.Markdown("# Lokaler Sprachassistent")
        gr.Markdown(
            "**STT:** Vosk  |  **LLM:** Gemma3 via Ollama  |  "
            "**TTS:** Piper / Thorsten (männlich, offline)"
        )
        gr.Markdown(
            "1. Sprechen → **Transkribieren**  "
            "2. Text prüfen/korrigieren  "
            "3. **Antwort anfordern**  "
            "(WAV von Tablet hochladen = Mikrofon-Test)"
        )

        with gr.Row():
            with gr.Column(scale=1):
                audio_input = gr.Audio(
                    sources=["microphone", "upload"],
                    type="filepath",
                    label="Hier sprechen oder WAV hochladen",
                    format="wav",
                    buttons=["download"],
                    waveform_options={"sample_rate": 16000},
                )
                transkribieren_btn = gr.Button("1. Transkribieren", variant="secondary")
                antwort_btn = gr.Button("2. Antwort anfordern", variant="primary")

            with gr.Column(scale=2):
                frage_out = gr.Textbox(
                    label="Erkannte Frage (korrigierbar vor dem Senden)",
                    lines=3,
                    interactive=True,
                )
                antwort_out = gr.Textbox(
                    label="Antwort (Gemma3)",
                    lines=5,
                    interactive=False,
                )
                audio_out = gr.Audio(
                    label="Antwort als Audio (Thorsten)",
                    type="filepath",
                    interactive=False,
                    autoplay=True,
                    buttons=["download"],
                )
                zeiten_out = gr.Textbox(
                    label="Zeitmessung",
                    lines=1,
                    interactive=False,
                )

        gr.Markdown("## Gesprächsverlauf")
        verlauf_tabelle = gr.Dataframe(
            headers=["Zeit", "Frage", "Antwort", "STT(s)", "LLM(s)", "TTS(s)", "Gesamt(s)"],
            label="Alle Gespräche",
            wrap=True,
        )

        transkribieren_btn.click(
            fn=transkribiere_fn,
            inputs=[audio_input],
            outputs=[frage_out, zeiten_out],
        )

        antwort_btn.click(
            fn=antworte_fn,
            inputs=[frage_out],
            outputs=[frage_out, antwort_out, audio_out, zeiten_out, verlauf_tabelle],
        )

        demo.load(fn=verlauf_fn, outputs=[verlauf_tabelle])

    return demo

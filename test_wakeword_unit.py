import json
import unittest

import numpy as np

from wakeword.wakeword_listener import (
    WakeWordListener,
    _build_grammar,
    _text_has_wake_word,
)


class WakeWordTextTests(unittest.TestCase):
    def test_accepts_only_short_computer_variants(self):
        wake_words = {"computer"}

        self.assertTrue(_text_has_wake_word("computer", wake_words))
        self.assertTrue(_text_has_wake_word("hey computer", wake_words))
        self.assertTrue(_text_has_wake_word("hallo komputer", wake_words))

        self.assertFalse(_text_has_wake_word("[unk]", wake_words))
        self.assertFalse(_text_has_wake_word("wie wird das wetter", wake_words))
        self.assertFalse(_text_has_wake_word("computer wie spaet ist es", wake_words))
        self.assertFalse(_text_has_wake_word("bonjour ordinateur", wake_words))

    def test_grammar_stays_limited_to_wake_phrases_and_unknown(self):
        grammar = json.loads(_build_grammar({"computer"}))

        self.assertIn("computer", grammar)
        self.assertIn("hey computer", grammar)
        self.assertIn("[unk]", grammar)
        self.assertNotIn("wie wird das wetter", grammar)


class WakeWordAudioTests(unittest.TestCase):
    def _listener_without_model(self):
        listener = object.__new__(WakeWordListener)
        listener._reset_audio_window()
        return listener

    def test_rejects_too_short_audio(self):
        listener = self._listener_without_model()
        audio = np.full(400, 0.02, dtype=np.float32)
        listener._track_audio_block(audio, 0.02)

        self.assertEqual(listener._wake_audio_reject_reason(), "zu kurz/Impuls")

    def test_accepts_plausible_short_speech_window(self):
        listener = self._listener_without_model()
        audio = np.full(400, 0.02, dtype=np.float32)
        for _ in range(12):
            listener._track_audio_block(audio, 0.02)

        self.assertIsNone(listener._wake_audio_reject_reason())

    def test_rejects_clipped_audio(self):
        listener = self._listener_without_model()
        audio = np.full(400, 1.0, dtype=np.float32)
        for _ in range(12):
            listener._track_audio_block(audio, 1.0)

        self.assertEqual(listener._wake_audio_reject_reason(), "uebersteuert")


if __name__ == "__main__":
    unittest.main()

import unittest

from art_kit import i18n


class I18nTest(unittest.TestCase):
    def tearDown(self):
        i18n.set_language("en")

    def test_missing_keys_fall_back_to_english(self):
        i18n.set_language("tr")
        self.assertEqual(i18n.t("save"), "KAYDET")
        self.assertEqual(i18n.t("pixels", n=4), "piksel 4")
        i18n.set_language("de")
        self.assertEqual(i18n.t("help"), "HILFE")
        i18n.set_language("pl")
        self.assertEqual(i18n.t("all"), "WSZYSTKO")

    def test_unknown_language_is_english(self):
        self.assertEqual(i18n.set_language("xx"), "en")
        self.assertEqual(i18n.t("save"), "SAVE")

    def test_every_translation_keeps_the_family_and_the_bold(self):
        """#v2.8.0: switching language may only move the point size, and only
        inside a box the widget has already frozen. Up to #v2.7.0 a long
        translation was handed `theme.FONT_SMALL`, which is a different size
        AND drops the weight, so the whole UI read as a different typeface."""
        from art_kit import theme
        for code in i18n.LANGS:
            i18n.set_language(code)
            for key in ("save", "draw", "with_grid", "new_drawing", "help", "export_png"):
                family, _size, *rest = i18n.font_for(key)
                self.assertEqual(family, theme.FONT_FAMILY, f"{code}/{key}")
                self.assertIn("bold", rest, f"{code}/{key}")

    def test_the_new_v28_keys_are_translated_everywhere(self):
        """A key that falls back to English in one language is the one that
        silently ships half-translated, so the four tables are compared."""
        for key in ("open_location", "bg_title", "bg_question", "bg_transparent",
                    "bg_white", "bg_colour", "cancel", "export", "ok", "yes", "no",
                    "cam_locked", "sign_title", "sign_question", "sign_corner",
                    "sign_watermark", "sign_corner_hint", "sign_watermark_hint",
                    "sign_no_artist", "sign_too_small", "meta_toggle", "log_toggle",
                    "snapshot_saved", "snapshot_failed", "n_chosen", "squint", "exported",
                    "saved_at", "new_title", "create", "resize_title", "resize", "size_hint",
                    "custom", "preset_flower", "preset_tree", "label_heading", "artist_heading",
                    "apply", "type_new", "rename_prompt", "delete_confirm", "fav_use",
                    "fav_remove", "import_title", "imported", "update_offer_self",
                    "update_offer_page", "save_error", "migrated_msg", "skipped_msg",
                    "look", "look_only", "gp_title", "gp_limits", "gp_corner", "gp_watermark",
                    "gp_meta", "gp_made", "gp_log", "gp_hash", "gp_engine", "gp_later",
                    "total_pixels", "empty_cell", "grid_white", "grid_black",
                    "rename_label_prompt", "rename_artist_prompt", "delete_label_confirm",
                    "delete_artist_confirm"):
            for code in i18n.LANGS:
                self.assertIn(key, i18n.STRINGS[code], f"{code} is missing {key}")

    def test_the_signature_hints_name_the_notice_in_every_language(self):
        for code in i18n.LANGS:
            i18n.set_language(code)
            for key in ("sign_corner_hint", "sign_watermark_hint"):
                self.assertIn("© 2026 Mir", i18n.t(key, notice="© 2026 Mir"), f"{code}/{key}")
            self.assertIn("x.png", i18n.t("snapshot_saved", name="x.png"), code)

    def test_every_language_has_every_key(self):
        """The sixth test pass found whole corners of the kit in English under
        every language; no table may be missing a key English has."""
        for code in i18n.LANGS:
            missing = set(i18n.STRINGS[i18n.EN]) - set(i18n.STRINGS[code])
            self.assertEqual(missing, set(), code)

    def test_every_placeholder_survives_translation(self):
        import string
        fields = lambda text: {f for _l, f, _s, _c in string.Formatter().parse(text) if f}
        for key, english in i18n.STRINGS[i18n.EN].items():
            for code in i18n.LANGS:
                self.assertEqual(fields(i18n.STRINGS[code][key]), fields(english), f"{code}/{key}")

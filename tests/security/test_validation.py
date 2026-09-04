import os

from meridian.security.validation import MAX_FIELD_CHARS, is_within_folder, truncate_field


def test_is_within_folder_true_for_a_normal_nested_file(tmp_path):
    folder = tmp_path / "notes"
    folder.mkdir()
    nested = folder / "sub" / "note.txt"
    nested.parent.mkdir()
    nested.write_text("hello")

    assert is_within_folder(nested, folder) is True


def test_is_within_folder_true_for_the_folder_itself(tmp_path):
    folder = tmp_path / "notes"
    folder.mkdir()

    assert is_within_folder(folder, folder) is True


def test_is_within_folder_false_for_a_symlink_escaping_the_folder(tmp_path):
    folder = tmp_path / "notes"
    folder.mkdir()
    outside_target = tmp_path / "outside.txt"
    outside_target.write_text("secret")
    symlink_path = folder / "escape.txt"
    os.symlink(outside_target, symlink_path)

    assert is_within_folder(symlink_path, folder) is False


def test_is_within_folder_false_for_an_unrelated_path(tmp_path):
    folder = tmp_path / "notes"
    folder.mkdir()
    unrelated = tmp_path / "other" / "file.txt"
    unrelated.parent.mkdir()
    unrelated.write_text("x")

    assert is_within_folder(unrelated, folder) is False


def test_truncate_field_leaves_short_values_untouched():
    assert truncate_field("hello") == "hello"


def test_truncate_field_caps_at_max_chars():
    value = "x" * (MAX_FIELD_CHARS + 100)

    result = truncate_field(value)

    assert len(result) == MAX_FIELD_CHARS


def test_truncate_field_respects_custom_max_chars():
    assert truncate_field("hello world", max_chars=5) == "hello"

from unittest.mock import Mock
import pytest
from patreon_mega_audit.update_posts import parser, editor_control


@pytest.mark.parametrize('language,accepted,rejected', [
    ('auto', ['Update', '更新'], ['Publish', 'Delete']),
    ('en', ['Update'], ['更新', 'Publish']),
    ('zh', ['更新'], ['Update', 'Delete']),
])
def test_language_selectors_are_exact(language, accepted, rejected):
    args = parser().parse_args(['--report', 'unused.json', '--editor-language', language])
    page = Mock()
    editor_control(page, 'button', 'update_button', args)
    pattern = page.get_by_role.call_args.kwargs['name']
    assert all(pattern.fullmatch(label) for label in accepted)
    assert all(not pattern.fullmatch(label) for label in rejected)


def test_explicit_override_and_missing_control():
    args = parser().parse_args(['--report', 'unused.json', '--update-button-name', 'Custom (save)'])
    page = Mock()
    page.get_by_role.return_value.wait_for.side_effect = RuntimeError('missing')
    with pytest.raises(RuntimeError, match='Patreon editor language'):
        editor_control(page, 'button', 'update_button', args)
    pattern = page.get_by_role.call_args.kwargs['name']
    assert pattern.fullmatch('Custom (save)')
    assert not pattern.fullmatch('Update')

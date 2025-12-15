import pytest
from app.core.security import check_filesystem_access


def test_allow_engineering_folder_for_eng():
    assert check_filesystem_access('eng01', '/Engineering/project/README.md') is True


def test_deny_sales_access_engineering():
    assert check_filesystem_access('sales01', '/Engineering/secret.txt') is False


def test_deny_traversal_attempt():
    # traversal segments should be rejected
    assert check_filesystem_access('it01', '/Engineering/../IT/secret.txt') is False
    assert check_filesystem_access('it01', '/Engineering/../../etc/passwd') is False


def test_empty_path_denied():
    assert check_filesystem_access('eng01', '') is False
    assert check_filesystem_access('eng01', None) is False

import os
from pathlib import Path
import pytest
from isp_app.config import load_mapping
from isp_app.models import Project

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

@pytest.fixture
def root(): return ROOT

@pytest.fixture
def mapping(): return load_mapping(ROOT)

@pytest.fixture
def project():
    p = Project(); p.fields['person.name'] = '検証用ダミー利用者'
    return p

@pytest.fixture(scope='session')
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])

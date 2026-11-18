import sys
from pathlib import Path

if not getattr(sys, 'frozen', False): sys.path.insert(0, str(Path(__file__).resolve().parent / 'src'))

def main():
    from PySide6.QtWidgets import QApplication
    from isp_app.ui.main_window import MainWindow
    app = QApplication(sys.argv)
    app.setApplicationName('個別支援計画'); app.setOrganizationName('LocalSupportTools')
    window = MainWindow(); window.show()
    if len(sys.argv) > 1 and Path(sys.argv[1]).suffix.lower() == '.isp': window.load_path(sys.argv[1])
    return app.exec()

if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception:
        import traceback, os
        log = Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'IndividualSupportPlan' / 'startup-error.txt'
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text(traceback.format_exc(), 'utf-8')
        raise

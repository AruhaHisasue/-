"""Excel COM in a dedicated instance. Always close the workbook and quit."""
from contextlib import contextmanager
from pathlib import Path
import shutil
import tempfile

def available():
    try:
        import winreg
        import win32com.client
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r'Excel.Application\CLSID'): pass
        return True, 'Excelによるプレビュー・印刷が利用できます'
    except (ImportError, OSError):
        return False, 'Microsoft Excelまたはpywin32がありません。Excel互換アプリで出力.xlsxを開いて確認してください。完全一致の印刷は保証できません。'

@contextmanager
def excel_book(path):
    import pythoncom
    import win32com.client
    pythoncom.CoInitialize()
    app = book = None
    try:
        app = win32com.client.DispatchEx('Excel.Application')
        app.DisplayAlerts = False
        app.AutomationSecurity = 3
        book = app.Workbooks.Open(str(Path(path).resolve()), UpdateLinks=0, ReadOnly=True)
        yield app, book
    finally:
        try:
            if book is not None: book.Close(SaveChanges=False)
        finally:
            book = None
            try:
                if app is not None: app.Quit()
            finally:
                app = None
                pythoncom.CoUninitialize()

def prepare_print(book, sheets, mapping):
    if not sheets: raise ValueError('印刷対象シートを選択してください')
    suggestions = {mapping['sheets']['assessment']: mapping['rules']['print_area_suggestion_assessment'],
                   mapping['sheets']['meeting']: mapping['rules']['print_area_suggestion_meeting']}
    for name in sheets:
        if name not in mapping['sheets'].values(): raise ValueError('未対応の印刷シートです')
        sheet = book.Worksheets(name)
        if not sheet.PageSetup.PrintArea and name in suggestions:
            sheet.PageSetup.PrintArea = suggestions[name]
        sheet = None
    book.Worksheets(tuple(sheets)).Select()

def print_workbook(path, sheets, mapping, mode='preview', pdf_path=None):
    ok, reason = available()
    if not ok: raise RuntimeError(reason)
    if mode not in ('preview', 'print', 'pdf'): raise ValueError('印刷モードが不正です')
    with tempfile.TemporaryDirectory(prefix='isp-print-') as folder:
        temporary = Path(folder) / 'print.xlsx'
        shutil.copyfile(path, temporary)
        with excel_book(temporary) as (app, book):
            prepare_print(book, sheets, mapping)
            if mode == 'pdf':
                if not pdf_path: raise ValueError('PDFの保存先が必要です')
                app.ActiveSheet.ExportAsFixedFormat(0, str(Path(pdf_path).resolve()))
            elif mode == 'preview':
                app.Visible = True
                app.ActiveWindow.SelectedSheets.PrintPreview()
            else:
                app.Visible = True
                # Native Excel dialog supplies printer choice, range and final print action.
                app.Dialogs(8).Show()  # xlDialogPrint

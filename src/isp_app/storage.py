"""Bounded JSON ZIP, atomic replacement; no extraction or executable deserialization."""
import hashlib
import json
import os
import tempfile
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED, BadZipFile
from .models import Project

MAX_SIZE = 20 * 1024 * 1024

def encoded(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False).encode('utf-8')

def save_project(project, path):
    Project.from_dict(project.to_dict())
    path = Path(path)
    if path.suffix.lower() != '.isp': raise ValueError('拡張子は .isp が必要です')
    payload = encoded(project.to_dict())
    attachments = encoded(project.attachments)
    if len(payload) + len(attachments) > MAX_SIZE: raise ValueError('保存データが上限20MBを超えています')
    manifest = {'format': 'individual-support-plan', 'schema_version': 1, 'encrypted': False,
        'created_at': project.created_at, 'updated_at': project.updated_at,
        'project_sha256': hashlib.sha256(payload).hexdigest(),
        'attachments_sha256': hashlib.sha256(attachments).hexdigest()}
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, suffix='.tmp')
    os.close(fd)
    try:
        with ZipFile(name, 'w', ZIP_DEFLATED) as z:
            z.writestr('manifest.json', encoded(manifest))
            z.writestr('project.json', payload)
            z.writestr('attachments/metadata.json', attachments)
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)

def load_project(path):
    try:
        with ZipFile(path) as z:
            names = z.namelist()
            if len(names) != 3 or set(names) != {'manifest.json', 'project.json', 'attachments/metadata.json'}:
                raise ValueError('コンテナの構成が不正です')
            if sum(i.file_size for i in z.infolist()) > MAX_SIZE or any(i.flag_bits & 1 for i in z.infolist()):
                raise ValueError('サイズ超過または未対応の暗号化です')
            manifest = json.loads(z.read('manifest.json'))
            if manifest.get('format') != 'individual-support-plan' or manifest.get('schema_version') != 1:
                raise ValueError('未対応のファイル形式です')
            payload, attachments = z.read('project.json'), z.read('attachments/metadata.json')
            if hashlib.sha256(payload).hexdigest() != manifest.get('project_sha256') or hashlib.sha256(attachments).hexdigest() != manifest.get('attachments_sha256'):
                raise ValueError('整合性検査に失敗しました')
            project = Project.from_dict(json.loads(payload))
            if project.attachments != json.loads(attachments): raise ValueError('添付メタデータが一致しません')
            return project
    except (BadZipFile, KeyError, TypeError, AttributeError, UnicodeError, json.JSONDecodeError, RecursionError, RuntimeError) as e:
        raise ValueError('破損または未対応の .isp ファイルです') from e

from copy import deepcopy

def transfer_fields(project, source, target, allowed_suffixes):
    """Copy common form values including explicit blanks; never infer consent evidence."""
    for suffix in allowed_suffixes:
        destination = target + '.' + suffix
        origin = source + '.' + suffix
        if origin in project.fields: project.fields[destination] = deepcopy(project.fields[origin])
        else: project.fields.pop(destination, None)
    project.settings['consent_confirmed'].pop(target, None)
    project.metadata['status'] = '下書き'

def report_pdf_upload_path(instance, filename):
    """Structured, non-guessable storage path, same convention as
    apps.documents.utils.document_upload_path -- version is part of the path
    so regenerating never overwrites a prior version's stored file."""
    return f'sprints/{instance.sprint_id}/reports/{instance.id}_v{instance.version}.pdf'


def report_docx_upload_path(instance, filename):
    return f'sprints/{instance.sprint_id}/reports/{instance.id}_v{instance.version}.docx'

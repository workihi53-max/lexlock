"""Run with the installed interpreter on a Windows runner after running the EXE."""
import argparse
import io
import json
import time
from pathlib import Path

import httpx
from docx import Document


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    root = parser.parse_args().root
    with httpx.Client(base_url='http://127.0.0.1:8765', timeout=30) as client:
        for attempt in range(60):
            try:
                response = client.get('/api/health')
                response.raise_for_status()
                health = response.json()
                break
            except httpx.HTTPError:
                if attempt == 59:
                    raise
                time.sleep(1)
        assert health['ok'] and health['offline'], health
        assert Path(health['workspace']).resolve() == (root / 'workspace').resolve(), health
        assert health['ollama'] and health['model_installed'], health
        response = client.get('/')
        response.raise_for_status()
        assert 'risk-side' in response.text
        files = [('files', (path.name, path.read_bytes(), 'text/plain'))
                 for path in sorted((root / 'samples').glob('*.txt'))]
        assert len(files) == 3
        response = client.post('/api/upload', files=files)
        response.raise_for_status()
        assert len(response.json()['saved']) == 3
        response = client.post('/api/scenario/fill', json={'out_name': 'install-smoke.docx'}, timeout=300)
        response.raise_for_status()
        result = response.json()
        assert result['ok'] and len(result['fields']) >= 23, result
        response = client.get('/api/download/install-smoke.docx')
        response.raise_for_status()
        document = Document(io.BytesIO(response.content))
        text = '\n'.join([p.text for p in document.paragraphs] + [
            cell.text for table in document.tables for row in table.rows for cell in row.cells])
        assert result['fields']['inn'] in text
        response = client.post('/api/scenario/fill', json={'out_name': '../outside.docx'})
        assert response.status_code == 400
    # This exercises actual local inference, not just presence of the model files.
    response = httpx.post('http://127.0.0.1:11434/api/generate', json={
        'model': health['model'], 'prompt': 'Ответь одним словом: готово',
        'stream': False, 'options': {'num_predict': 16}}, timeout=300)
    response.raise_for_status()
    assert response.json().get('response', '').strip(), response.text
    print(json.dumps({'result': 'passed', 'model': health['model'],
                      'checks': ['EXE installation', 'launcher', 'offline API', 'upload',
                                 'fill and download DOCX', 'path validation', 'live inference']}, ensure_ascii=False))


if __name__ == '__main__':
    main()

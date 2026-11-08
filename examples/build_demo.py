"""Run from the project root: python -m examples.build_demo."""
import json
from datetime import datetime, timezone
from pathlib import Path
from backend import fuzzy as F
from backend.clustering import analyze


def main():
    folder = Path('examples')
    folder.mkdir(exist_ok=True)
    items = F.generate(150, 42)
    options = dict(mode='fixed', metric='cuts', k=3)
    result = analyze(items, options)
    project = dict(format='weibull-lab', version=1, epsilon=F.EPS, levels=F.LEVELS,
                   items=items, analysisOptions=options,
                   logs=[dict(time=datetime.now(timezone.utc).isoformat(), action='Демонстрационный набор',
                              details=dict(backend='Python / FastAPI', count=150, seed=42, k=3, metric='cuts'))])
    a, b = F.weibull('A', 2, 3), F.weibull('B', 3, 2, 1)
    operations = []
    for op in ['+', '-', '*', '/']:
        value = F.arithmetic(a, b, op)
        operations.append(dict(operation=op, centroid=value['centroid'], alphaHalf=value['cuts'][50]))
    calculations = dict(a=dict(shape=2, scale=3, shift=0), b=dict(shape=3, scale=2, shift=1),
                        operations=operations, comparison=F.compare(a, b))
    for name, data in [('demo-project.json', project), ('clustering-result.json', result),
                       ('calculations.json', calculations)]:
        (folder / name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    summary = dict(sizes=list(map(len, result['groups'])), silhouette=result['silhouette'],
                   inertia=result['inertia'], iterations=result['iterations'])
    (folder / 'demo-session.log').write_text('Weibull Lab / Python\nN=150; seed=42; k=3; metric=cuts\n' +
        '\n'.join(json.dumps(v, ensure_ascii=False) for v in [summary, *operations]), encoding='utf-8')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()

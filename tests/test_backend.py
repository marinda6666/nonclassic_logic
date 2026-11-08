"""Numerical tests and actual HTTP requests through FastAPI's TestClient."""
import math
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from backend import fuzzy as F
from backend.clustering import analyze
from backend.main import app


class FuzzyTests(unittest.TestCase):
    def setUp(self):
        self.a = F.weibull('A', 2, 3)
        self.b = F.weibull('B', 3, 2, 1)

    def test_normalization_and_nested_cuts(self):
        for shape in [1, 1.001, 1.5, 2, 5, 20]:
            for scale in [.05, 1, 1000]:
                v = F.weibull('x', shape, scale, -2)
                F.validate(dict(name='cuts', type='cuts', cuts=v['cuts']))
                self.assertAlmostEqual(F.membership(v, v['cuts'][100][0]), 1)
                for i in [0, 1, 25, 50, 75, 99]:
                    l, r = v['cuts'][i]
                    if shape > 1 and l - v['shift'] > 1e-10:
                        self.assertAlmostEqual(F.membership(v, l), F.LEVELS[i], delta=1e-6)
                    self.assertAlmostEqual(F.membership(v, r), F.LEVELS[i], delta=1e-6)

    def test_known_exponential_and_rayleigh_values(self):
        v = F.weibull('E', 1, 3, 2)
        self.assertAlmostEqual(v['cuts'][50][1], 2 + 3 * math.log(2))
        self.assertAlmostEqual(v['centroid'], 5, delta=.01)
        self.assertAlmostEqual(self.a['centroid'], 3 * math.sqrt(math.pi) / 2, delta=.01)

    def test_arithmetic_intervals_and_signs(self):
        for shift in [-20, -2, 2]:
            b = F.weibull('B', 2, 1, shift)
            for op in ['+', '-', '*'] + (['/'] if shift == 2 else []):
                result = F.arithmetic(self.a, b, op)
                F.validate(result)
                for i, ((l, r), (s, t)) in enumerate(zip(self.a['cuts'], b['cuts'])):
                    if op == '+':
                        expected = [l + s, r + t]
                    elif op == '-':
                        expected = [l - t, r - s]
                    else:
                        values = [l * s, l * t, r * s, r * t] if op == '*' else [l / s, l / t, r / s, r / t]
                        expected = [min(values), max(values)]
                    self.assertEqual(result['cuts'][i], expected)

    def test_zero_division_rejected(self):
        with self.assertRaisesRegex(ValueError, 'ноль'):
            F.arithmetic(self.a, F.weibull('Z', 2, 1, -.5), '/')

    def test_generation_boundaries_and_seed(self):
        for count in [100, 150, 300]:
            self.assertEqual(len(F.generate(count, 42)), count)
        self.assertEqual(F.generate(100, 42), F.generate(100, 42))
        self.assertNotEqual(F.generate(100, 42), F.generate(100, 43))
        for count in [99, 301, 100.5]:
            with self.assertRaises(ValueError):
                F.generate(count)

    def test_generated_parameters_have_no_index_groups(self):
        # Guard against the old modulo-three parameter bands.
        for seed in [0, 42, 4294967295]:
            values = F.generate(300, seed)
            for offset in range(3):
                group = values[offset::3]
                self.assertTrue(all(1 <= v['shape'] < 6 and .5 <= v['scale'] < 10
                                    and v['shift'] == 0 for v in group))
                self.assertLess(min(v['shape'] for v in group), 2)
                self.assertGreater(max(v['shape'] for v in group), 5)
                self.assertLess(min(v['scale'] for v in group), 2)
                self.assertGreater(max(v['scale'] for v in group), 8)

    def test_distance_and_comparison(self):
        self.assertEqual(F.distance(self.a, self.a), 0)
        self.assertEqual(F.compare(self.a, self.a)['relation'], '≈')
        self.assertAlmostEqual(F.distance(self.a, self.b), F.distance(self.b, self.a))

    def test_invalid_parameters_and_nested_import(self):
        for shape, scale in [(.5, 1), (2, 0), (math.nan, 2)]:
            with self.assertRaises(ValueError):
                F.weibull('bad', shape, scale)
        bad = F.arithmetic(self.a, self.b, '+')
        bad['cuts'][50] = [1e6, 1e7]
        with self.assertRaisesRegex(ValueError, 'вложенными'):
            F.validate(bad)

    def test_kmeans_on_known_separated_groups(self):
        # Test clustering on an explicit fixture, independently of the generator.
        values = [F.weibull(str(i), 2, 1, shift + i*.01)
                  for shift in [0, 10, 20] for i in range(10)]
        for metric in ['cuts', 'center']:
            result = analyze(values, dict(k=3, metric=metric))
            self.assertEqual(sorted(map(len, result['groups'])), [10, 10, 10])
            self.assertEqual(len(set(sum(result['groups'], []))), 30)
            self.assertGreater(result['silhouette'], .7)
            self.assertTrue(result['converged'])
            self.assertEqual(result, analyze(values, dict(k=3, metric=metric)))

    def test_identical_objects_and_edge_k(self):
        for k in [1, 3, 10]:
            result = analyze([self.a] * 10, dict(k=k))
            self.assertEqual(len(result['groups']), k)
            self.assertTrue(all(result['groups']))
            self.assertAlmostEqual(result['inertia'], 0)
        for k in [0, 3]:
            with self.assertRaises(ValueError):
                analyze([self.a, self.b], dict(k=k))

    def test_single_link_chain(self):
        values = [F.weibull(str(s), 2, 1, s) for s in [0, 1, 2, 10]]
        result = analyze(values, dict(mode='threshold', threshold=1.01))
        self.assertEqual(list(map(len, result['groups'])), [3, 1])
        self.assertEqual(len(analyze(values, dict(mode='threshold', threshold=0))['groups']), 4)

    def test_alpha_cut_interpolation_and_boundaries(self):
        # Linear triangular memberships have exact off-grid interval boundaries.
        v = F.validate(dict(name='triangle', type='cuts',
                            cuts=[[a, 2-a] for a in F.LEVELS]))
        for alpha in [F.EPS, .12345, .5, 1]:
            l, r = F.alpha_cut(v, alpha)
            self.assertAlmostEqual(l, alpha)
            self.assertAlmostEqual(r, 2-alpha)
        self.assertEqual(F.alpha_cut(self.a, .5), self.a['cuts'][50])
        for alpha in [0, -1, 1.01, math.nan, math.inf, True]:
            with self.assertRaises(ValueError):
                F.alpha_cut(v, alpha)

    def test_alpha_level_changes_partition_in_both_modes(self):
        # Same mode at x=0, different widths: at alpha=1 they coincide.
        values = [F.weibull('narrow', 1, 1), F.weibull('wide', 1, 5),
                  F.weibull('shifted', 1, 1, 1)]
        for mode in ['fixed', 'threshold']:
            options = dict(metric='alpha', mode=mode, k=2, threshold=.2)
            low = analyze(values, dict(options, alpha=.5))
            high = analyze(values, dict(options, alpha=1))
            self.assertNotEqual(low['labels'][0], low['labels'][1])
            self.assertEqual(high['labels'][0], high['labels'][1])
            self.assertEqual(high['alpha'], 1)
        self.assertAlmostEqual(analyze(values[:2], dict(metric='alpha', k=1, alpha=.5))['inertia'],
                               4 * math.log(2)**2)


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.a = dict(name='A', type='weibull', shape=2, scale=3, shift=0)
        cls.b = dict(name='B', type='weibull', shape=3, scale=2, shift=1)

    def post(self, url, body):
        response = self.client.post(url, json=body)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_health_config_and_openapi(self):
        self.assertEqual(self.client.get('/healthz').json()['backend'], 'python-fastapi')
        self.assertEqual(len(self.client.get('/api/config').json()['levels']), 101)
        schema = self.client.get('/api/openapi.json').json()
        self.assertIn('/api/cluster', schema['paths'])

    def test_api_generate_and_cluster(self):
        items = self.post('/api/generate', dict(count=150, seed=42))['items']
        result = self.post('/api/cluster', dict(items=items, options=dict(k=3)))
        self.assertEqual(len(result['groups']), 3)
        self.assertEqual(sorted(sum(result['groups'], [])), list(range(150)))

    def test_api_random_seed_and_reproduction(self):
        with patch('backend.main.secrets.randbits', side_effect=[123, 456]) as entropy:
            a = self.post('/api/generate', dict(count=100))
            b = self.post('/api/generate', dict(count=100, seed=None))
        self.assertEqual(entropy.call_count, 2)
        self.assertEqual((a['seed'], b['seed']), (123, 456))
        self.assertNotEqual(a['items'], b['items'])
        repeated = self.post('/api/generate', dict(count=100, seed=a['seed']))
        self.assertEqual(repeated, a)
        with patch('backend.main.secrets.randbits') as entropy:
            self.assertEqual(self.post('/api/generate', dict(count=100, seed=0))['seed'], 0)
            entropy.assert_not_called()

    def test_api_arithmetic_and_compare(self):
        for op in ['+', '-', '*', '/', 'compare']:
            result = self.post('/api/operations', dict(a=self.a, b=self.b, operation=op))
            self.assertIn('relation' if op == 'compare' else 'centroid', result)

    def test_api_alpha_and_project_roundtrip(self):
        options = dict(metric='alpha', alpha=.73456, k=2)
        items = [self.a, self.b]
        result = self.post('/api/cluster', dict(items=items, options=options))
        self.assertEqual(result['alpha'], options['alpha'])
        project = dict(format='weibull-lab', version=1, epsilon=F.EPS, levels=F.LEVELS,
                       items=items, analysisOptions=options)
        self.assertEqual(self.post('/api/projects/validate', project)['analysis'], result)
        for alpha in [0, -1, 1.001, None]:
            self.assertEqual(self.client.post('/api/cluster', json=dict(
                items=items, options=dict(options, alpha=alpha))).status_code, 422)

    def test_api_rejects_zero_invalid_count_and_shape(self):
        zero = dict(name='Z', shape=2, scale=1, shift=-.5)
        response = self.client.post('/api/operations', json=dict(a=self.a, b=zero, operation='/'))
        self.assertEqual(response.status_code, 422)
        self.assertIn('ноль', response.json()['detail'])
        for body in [dict(count=99), dict(count=301), dict(count=100.5), dict(seed=-1)]:
            self.assertEqual(self.client.post('/api/generate', json=body).status_code, 422)
        self.assertEqual(self.client.post('/api/values', json=dict(name='x', shape=.5, scale=1)).status_code, 422)

    def test_server_recomputes_centroid_and_original_cuts(self):
        forged = dict(self.a, cuts=[[999, 999]] * 101, centroid=-1)
        result = self.post('/api/values', forged)
        self.assertNotEqual(result['cuts'][50], [999, 999])
        self.assertAlmostEqual(result['centroid'], F.weibull('A', 2, 3)['centroid'])

    def test_project_validation_and_grid_rejection(self):
        items = self.post('/api/generate', dict(count=100, seed=42))['items']
        body = dict(format='weibull-lab', version=1, epsilon=F.EPS, levels=F.LEVELS,
                    items=items, analysisOptions=dict(k=3), logs=[])
        result = self.post('/api/projects/validate', body)
        self.assertEqual(len(result['items']), 100)
        self.assertEqual(len(result['analysis']['groups']), 3)
        body['levels'] = [0] * 101
        self.assertEqual(self.client.post('/api/projects/validate', json=body).status_code, 422)


if __name__ == '__main__':
    unittest.main()

import tempfile
import unittest

import mock

from chainer import serializers
from chainer import testing
from chainer.training import extensions
from chainer.training.util import get_trigger


def _get_mocked_trainer(init):
    trainer = mock.Mock()

    def update():
        trainer.updater.iteration += 1
    trainer.updater.iteration = 0
    trainer.updater.update = update

    trainer.updater.optimizer.x = init
    trainer.updater.get_optimizer = lambda _: trainer.updater.optimizer

    return trainer


@testing.parameterize(
    {'init': 2.0, 'rate': 0.5, 'target': None, 'expect': [2.0, 1.0, 0.5]},
    {'init': 2.0, 'rate': 0.5, 'target': 1.2, 'expect': [2.0, 1.2, 1.2]},
    {'init': -2.0, 'rate': 0.5, 'target': -1.2, 'expect': [-2.0, -1.2, -1.2]},
    {'init': 2.0, 'rate': 2.0, 'target': None, 'expect': [2.0, 4.0, 8.0]},
    {'init': 2.0, 'rate': 2.0, 'target': 3.0, 'expect': [2.0, 3.0, 3.0]},
    {'init': -2.0, 'rate': 2.0, 'target': -3.0, 'expect': [-2.0, -3.0, -3.0]},
)
class TestExponentialShift(unittest.TestCase):

    def setUp(self):
        self.trainer = _get_mocked_trainer(self.init)

        self.interval = 4
        self.expect = [e for e in self.expect for _ in range(self.interval)]
        self.trigger = get_trigger((self.interval, 'iteration'))

    def _run_trainer(self, extension, expect, optimizer=None):
        if optimizer is None:
            optimizer = self.trainer.updater.optimizer

        if extension.invoke_before_training:
            extension(self.trainer)

        for e in self.expect:
            self.trainer.updater.update()
            self.assertEqual(optimizer.x, e)
            if self.trigger(self.trainer):
                extension(self.trainer)

    def test_basic(self):
        extension = extensions.ExponentialShift(
            'x', self.rate, target=self.target)
        self._run_trainer(extension, self.expect)

    def test_serialize(self):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            extension = extensions.ExponentialShift(
                'x', self.rate, target=self.target)
            self._run_trainer(extension, self.expect[:len(self.expect) // 2])
            serializers.save_npz(f.name, extension)

            extension = extensions.ExponentialShift(
                'x', self.rate, target=self.target)
            serializers.load_npz(f.name, extension)
            self._run_trainer(extension, self.expect[len(self.expect) // 2:])

    def test_with_init(self):
        self.trainer.updater.optimizer.x = 0
        extension = extensions.ExponentialShift(
            'x', self.rate, init=self.init, target=self.target)
        self._run_trainer(extension, self.expect)

    def test_with_optimizer(self):
        optimizer = mock.Mock()
        optimizer.x = self.init
        extension = extensions.ExponentialShift(
            'x', self.rate, target=self.target, optimizer=optimizer)
        self._run_trainer(extension, self.expect, optimizer)


class TestExponentialShiftInvalidArgument(unittest.TestCase):

    def test_negative_rate(self):
        with self.assertRaises(ValueError):
            extensions.ExponentialShift('x', -1.0)


testing.run_module(__name__, __file__)

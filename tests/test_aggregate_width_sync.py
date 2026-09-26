"""Single-width rounds must not leave stale server models for later recovery."""
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "sfl"))
HAS_TORCH = importlib.util.find_spec("torch") is not None


@unittest.skipUnless(HAS_TORCH, "requires torch for actual tensor-state verification")
class WidthSynchronizationTests(unittest.TestCase):
    def test_one_trained_width_updates_preexisting_and_new_widths(self):
        import torch
        from fed_server import Aggregator, slice_into
        for trained_width in (.5, 1.):
            with self.subTest(trained_width=trained_width):
                agg = Aggregator(SimpleNamespace(device="cpu", arch="cnn", cut=2, lr=.05, lr_decay="none"))
                agg.srv(.5)
                with torch.no_grad():
                    for model in agg.smodels.values():
                        for p in model.parameters():
                            p.fill_(1.)
                    for p in agg.smodels[trained_width].parameters():
                        p.fill_(2.)
                learned = {k: v.clone() for k, v in agg.smodels[trained_width].state_dict().items()}
                agg.aggregate({}, {trained_width: 4})
                # The just-trained region must exist in the canonical full model.
                full = agg.smodels[1.].state_dict()
                for key, value in slice_into(learned, full).items():
                    torch.testing.assert_close(value, learned[key])
                # Existing .5 and newly materialized .75 both inherit current state.
                for width in (.5, .75):
                    state = agg.srv(width)[0].state_dict()
                    for key, expected in slice_into(state, full).items():
                        torch.testing.assert_close(state[key], expected)


if __name__ == "__main__":
    unittest.main()

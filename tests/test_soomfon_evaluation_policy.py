from __future__ import annotations

import pytest

from dspx.services import soomfon_evaluation_runtime as soomfon_runtime


@pytest.mark.parametrize(
    "source",
    [
        "import os\ndef build_program():\n    return os.fork()\n",
        "import os\ndef escape():\n    return os.setsid()\n",
        "from os import fork\ndef escape():\n    return fork()\n",
        "import os\ndef escape():\n    return os.__dict__['fork']()\n",
        ("import os\ndef escape():\n    return getattr(os, ''.join(('for', 'k')))()\n"),
        (
            "import os\ndef escape():\n"
            "    dynamic = getattr\n"
            "    return dynamic(os, 'setsid')()\n"
        ),
        (
            "import os\ndef invoke(callable_value):\n"
            "    return callable_value()\n"
            "def escape():\n    return invoke(os.fork)\n"
        ),
        (
            "import os\ndef escape():\n"
            "    dynamic = getattr\n"
            "    alias = dynamic\n"
            "    return alias(os, 'fork')()\n"
        ),
        "import os\ndef escape():\n    return os.open('/x', os.O_RDONLY)\n",
        ("from pathlib import Path\ndef escape():\n    return Path('/x').open()\n"),
        (
            "import dspy\ndef escape():\n"
            "    module = dspy.__builtins__['__import__']('subprocess')\n"
            "    return module.Popen(['/bin/true'], start_new_session=True)\n"
        ),
        "import dspy\ndef escape():\n    return dspy.__builtins__['open']('/x')\n",
        "import os\ndef escape():\n    return os.makedirs('/x')\n",
        "import os\ndef escape():\n    return os.removedirs('/x')\n",
        "import os\ndef escape():\n    return os.renames('/x', '/y')\n",
        "import os\ndef escape():\n    return os.write(2, b'x')\n",
        "import os\ndef escape():\n    return os.pwrite(2, b'x', 0)\n",
        (
            "import typing\ndef escape():\n"
            "    module = typing.sys.modules['subprocess']\n"
            "    return module.call(['/bin/true'])\n"
        ),
        (
            "import typing\ndef escape():\n"
            "    module = typing.sys.modules['os']\n"
            "    return module.setxattr('/x', 'user.x', b'y')\n"
        ),
        "import dspy\ndef escape():\n    return dspy.LM('other-model')\n",
        "import dspy\ndef escape():\n    return dspy.configure(lm=None)\n",
        "import dspy\ndef build_program():\n    return dspy.ProgramOfThought('x -> y')\n",
        "import dspy\ndef escape():\n    return dspy.Image('http://x', download=True)\n",
        (
            "import dspy\ndef escape():\n"
            "    image_type = dspy.Image\n"
            "    return image_type.from_url('http://x')\n"
        ),
        (
            "import dspy\ndef build_program():\n"
            "    program = dspy.Predict('x -> y')\n"
            "    program.save('/x')\n"
            "    return program\n"
        ),
        (
            "import dspy\ndef build_program():\n"
            "    program = dspy.Module()\n"
            "    program.save('/x')\n"
            "    return program\n"
        ),
        "import dspy\ndef escape():\n    return dspy.Audio.from_url('http://x')\n",
        (
            "from dspy import Signature as S\ndef escape():\n"
            "    return S.parse_file('/x', content_type='application/pickle', "
            "allow_pickle=True)\n"
        ),
        (
            "def escape():\n    try:\n        raise RuntimeError()\n"
            "    except RuntimeError as exc:\n"
            "        return exc.__traceback__.tb_frame.f_globals['__builtins__']\n"
        ),
        (
            "def donor():\n    return None\ndef escape():\n"
            "    return type(donor.__code__)(donor.__code__.co_argcount)\n"
        ),
        "def build_program():\n    fn = breakpoint\n    return fn()\n",
        (
            "import dspy\ndef build_program():\n    fn = delattr\n"
            "    fn(dspy, 'settings')\n    return dspy.Predict('x -> y')\n"
        ),
        (
            "import dspy\ndef build_program():\n    len = delattr\n"
            "    len(dspy, 'settings')\n    return dspy.Predict('x -> y')\n"
        ),
        (
            "import dspy\ndef invoke(len):\n    len(dspy, 'settings')\n"
            "def build_program():\n    invoke(delattr)\n"
            "    return dspy.Predict('x -> y')\n"
        ),
        (
            "import dspy\ndef build_program():\n"
            "    delattr.__call__(dspy, 'settings')\n"
            "    return dspy.Predict('x -> y')\n"
        ),
    ],
)
def test_snapshot_policy_rejects_process_escape(source: str) -> None:
    with pytest.raises(ValueError, match="safety policy failed"):
        soomfon_runtime._validate_snapshot_sources({"program": source})

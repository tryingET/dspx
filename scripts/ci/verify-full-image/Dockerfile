# summary: "Base OS and tools for the optional hermetic verify-full run (AK-5754)."
# Python, the venv, prek, hook caches and docs tooling are NOT in this image: they are
# mounted read-only from the reviewed closure. The image supplies only the base OS and
# the generic tools the stages call by absolute path.
# Build (network is needed here, and only here):
#   docker build -t dspx-verify-full:local scripts/ci/verify-full-image
FROM archlinux:base
# cue: `just doctor` and the CUE contract tests. openssh: release-owner tests call ssh-keygen. python: the gate's own --plan self-tests
# start /usr/bin/python3 -I -S -B. The passwd entry: code under test calls getpwuid(1000).
RUN pacman -Syu --noconfirm --needed git just nodejs uv openssh python cue \
    && pacman -Scc --noconfirm \
    && rm -rf /var/cache/pacman/pkg/* /var/lib/pacman/sync/* \
    && useradd --uid 1000 --user-group --no-create-home --home-dir /home/tryinget \
         --shell /bin/bash tryinget \
    && install -d -o 1000 -g 1000 -m 0755 /home/tryinget \
    && git --version && just --version && node --version && uv --version \
    && ssh-keygen -V 2>&1 | head -1; /usr/bin/python3 --version
# The gate requires an image environment of PATH/LANG/LC_ALL only and no volumes.
ENV LANG=C.UTF-8

FROM mcr.microsoft.com/devcontainers/python:1-3.12-bullseye

ARG USERNAME=vscode

COPY uv.lock /tmp/uv.lock

# install uv version from uv.lock
RUN /usr/local/bin/python -m pip install \
    uv==$(awk '/^name = "uv"/,/^version =/' /tmp/uv.lock | awk -F\" '/^version =/ {print $2}') \
    && rm -rf /tmp/uv.lock

RUN SNIPPET="export PROMPT_COMMAND='history -a' && export HISTFILE=/commandhistory/.bash_history" \
    && mkdir /commandhistory \
    && touch /commandhistory/.bash_history \
    && chown -R $USERNAME /commandhistory \
    && echo "$SNIPPET" >> "/home/$USERNAME/.bashrc"

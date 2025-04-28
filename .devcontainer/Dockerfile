FROM mcr.microsoft.com/devcontainers/python:1-3.12-bullseye

ARG USERNAME=vscode

RUN /usr/local/bin/python -m pip install \
    uv

RUN SNIPPET="export PROMPT_COMMAND='history -a' && export HISTFILE=/commandhistory/.bash_history" \
    && mkdir /commandhistory \
    && touch /commandhistory/.bash_history \
    && chown -R $USERNAME /commandhistory \
    && echo "$SNIPPET" >> "/home/$USERNAME/.bashrc"

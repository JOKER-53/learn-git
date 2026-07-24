FROM alpine:3.20

RUN apk add --no-cache git bash curl ttyd

# Persisted repo lives on a mounted volume at /workspace-data
RUN mkdir -p /workspace-data/repo
WORKDIR /workspace-data/repo

RUN git config --global user.email "student@learn-git.local" && \
    git config --global user.name "Student" && \
    git config --global init.defaultBranch main

COPY credits.sh /usr/local/bin/credits.sh
RUN chmod +x /usr/local/bin/credits.sh

EXPOSE 7681
# ttyd exposes a real bash shell, rooted in the student's repo, over the browser.
# credits.sh rolls a one-time intro, then execs into a normal shell.
CMD ["ttyd", "-p", "7681", "-W", "bash", "/usr/local/bin/credits.sh"]

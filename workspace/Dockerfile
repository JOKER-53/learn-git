FROM alpine:3.20

RUN apk add --no-cache git bash curl ttyd

# All per-student volumes are mounted at /data (shared students_data volume).
# Each container only ever touches its own subfolder: /data/$REG_NO/repo.
# REG_NO is injected as an env var by workspace_manager.py when this
# container is created for a specific student.
WORKDIR /data

RUN git config --global user.email "student@learn-git.local" && \
    git config --global user.name "Student" && \
    git config --global init.defaultBranch main

COPY credits.sh /usr/local/bin/credits.sh
RUN chmod +x /usr/local/bin/credits.sh

EXPOSE 7681
# ttyd exposes a real bash shell, rooted in this student's own repo folder.
# credits.sh rolls a one-time intro, then execs into a normal shell there.
CMD ["ttyd", "-p", "7681", "-W", "bash", "/usr/local/bin/credits.sh"]

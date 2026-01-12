FROM debian:bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends openssh-server ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /run/sshd \
    && useradd -m -s /bin/bash demo \
    && echo "demo:demo123" | chpasswd \
    && sed -i 's/^#\\?PasswordAuthentication .*/PasswordAuthentication yes/g' /etc/ssh/sshd_config \
    && sed -i 's/^#\\?PermitRootLogin .*/PermitRootLogin no/g' /etc/ssh/sshd_config \
    && sed -i 's/^#\\?PubkeyAuthentication .*/PubkeyAuthentication yes/g' /etc/ssh/sshd_config \
    && sed -i 's/^#\\?UsePAM .*/UsePAM no/g' /etc/ssh/sshd_config

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 22

ENTRYPOINT ["/entrypoint.sh"]


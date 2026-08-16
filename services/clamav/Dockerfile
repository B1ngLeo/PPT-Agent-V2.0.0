# syntax=docker/dockerfile:1.7
FROM python@sha256:a3e58f9399353be051735f09be0316bfdeab571a5c6a24fd78b92df85bcb2d85

ARG CLAMAV_VERSION=1.4.3+dfsg-1~deb12u2

RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
       clamav-daemon=${CLAMAV_VERSION} \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /var/lib/instant-ppt-clamav \
    && chown clamav:clamav /var/lib/instant-ppt-clamav

COPY --chown=clamav:clamav services/clamav/clamd.conf /etc/clamav/clamd.conf
COPY --chown=clamav:clamav services/clamav/instant-ppt-test.ndb /var/lib/instant-ppt-clamav/instant-ppt-test.ndb
COPY --chmod=0555 services/clamav/clamd-health.py /usr/local/bin/clamd-health.py

USER clamav:clamav
EXPOSE 3310
ENTRYPOINT ["clamd", "--foreground=true", "--config-file=/etc/clamav/clamd.conf"]

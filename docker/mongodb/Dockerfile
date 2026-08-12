FROM mongo:7

# Single-node replica set is required for multi-document transactions (see
# docs/decisions/DECISIONS.md). rs.initiate() runs once via deployment's mongo-init service.
COPY docker/mongodb/mongod.conf /etc/mongod.conf

CMD ["mongod", "--config", "/etc/mongod.conf", "--replSet", "rs0", "--bind_ip_all"]

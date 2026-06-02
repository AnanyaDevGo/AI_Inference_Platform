#!/usr/bin/env bash
set -euo pipefail

# Configuration
NAMESPACE="infervoyage-dev"
SECRET_NAME="infervoyage-tls-cert"
DOMAIN="infervoyage.local"
OUTPUT_DIR="$(dirname "$0")/certs"

echo "=== Generating SSL/TLS Certificates for ${DOMAIN} ==="
mkdir -p "${OUTPUT_DIR}"

# Create OpenSSL SAN configuration file
SAN_CNF="${OUTPUT_DIR}/openssl-san.cnf"
cat <<EOF > "${SAN_CNF}"
[req]
distinguished_name = req_distinguished_name
req_extensions = v3_req
prompt = no

[req_distinguished_name]
C = US
ST = California
L = San Francisco
O = InferVoyage
OU = Development
CN = ${DOMAIN}

[v3_req]
keyUsage = keyEncipherment, dataEncipherment
extendedKeyUsage = serverAuth
subjectAltName = @alt_names

[alt_names]
DNS.1 = ${DOMAIN}
DNS.2 = localhost
IP.1 = 127.0.0.1
EOF

# Generate private key and self-signed certificate
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout "${OUTPUT_DIR}/tls.key" \
  -out "${OUTPUT_DIR}/tls.crt" \
  -config "${SAN_CNF}" \
  -extensions v3_req

echo "Certificates generated successfully in ${OUTPUT_DIR}"

# Check if kubectl is available
if ! command -v kubectl &> /dev/null; then
  echo "WARNING: kubectl not found in path. Please manually create the secret with:"
  echo "  kubectl create secret tls ${SECRET_NAME} --key=${OUTPUT_DIR}/tls.key --cert=${OUTPUT_DIR}/tls.crt -n ${NAMESPACE}"
  exit 0
fi

echo "=== Applying TLS secret to Kubernetes namespace: ${NAMESPACE} ==="
# Delete existing secret if it exists
kubectl delete secret "${SECRET_NAME}" -n "${NAMESPACE}" --ignore-not-found

# Create new secret
kubectl create secret tls "${SECRET_NAME}" \
  --key="${OUTPUT_DIR}/tls.key" \
  --cert="${OUTPUT_DIR}/tls.crt" \
  -n "${NAMESPACE}"

echo "Kubernetes TLS Secret '${SECRET_NAME}' created/updated successfully in namespace '${NAMESPACE}'."

# Clean up configuration file
rm -f "${SAN_CNF}"
echo "Cleanup completed."

#!/bin/bash

# Generate RS256 JWT keypair for FastAPI authentication

echo "Generating RS256 JWT keypair..."

# Create keys directory if it doesn't exist
mkdir -p ../keys

# Generate private key (4096-bit RSA)
openssl genrsa -out ../keys/jwt_private.pem 4096

# Extract public key
openssl rsa -in ../keys/jwt_private.pem -pubout -out ../keys/jwt_public.pem

echo "✅ JWT keys generated successfully!"
echo "  - Private key: keys/jwt_private.pem"
echo "  - Public key: keys/jwt_public.pem"
echo ""
echo "⚠️  IMPORTANT: Keep jwt_private.pem secure! Add keys/ to .gitignore"

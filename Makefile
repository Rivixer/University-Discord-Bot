.PHONY: proto-python

VERSION ?= v1
PROTO_DIR = shared/proto/
OUT_PY = shared/python/shared/gen/

PROTO_FILES := $(shell find $(PROTO_DIR) -name "*.proto")
GRPC_PROTO_FILES := $(shell grep -l 'service ' $(PROTO_FILES))
PROTOC_GEN_MYPY := $(shell which protoc-gen-mypy)
PROTOC := $(shell which protoc)

# Requirements: pip install grpcio-tools mypy-protobuf
proto-python:
	@echo "Generating Python gRPC code from Protobuf files…"
	@python -m grpc_tools.protoc -I$(PROTO_DIR) --python_out=$(OUT_PY) --pyi_out=$(OUT_PY) $(PROTO_FILES)
	@python -m grpc_tools.protoc -I$(PROTO_DIR) --grpc_python_out=$(OUT_PY) $(GRPC_PROTO_FILES)
	@$(PROTOC) -I$(PROTO_DIR) --mypy_out=$(OUT_PY) --plugin=protoc-gen-mypy=$(PROTOC_GEN_MYPY) $(PROTO_FILES)
	@$(PROTOC) -I$(PROTO_DIR) --mypy_grpc_out=$(OUT_PY) --plugin=protoc-gen-mypy=$(PROTOC_GEN_MYPY) $(GRPC_PROTO_FILES)

	@echo "Fixing imports…"
	@find $(OUT_PY) -name '*_pb2_grpc.py' -o -name '*_pb2.py'| \
	  xargs sed -i \
	    -e 's/^import \([a-z0-9_]*_pb2\)/from . import \1/' \
	    -e 's/^from \(.*\) import \([a-z0-9_]*_pb2\)/from . import \2/'
	@find $(OUT_PY) \( -name '*_pb2_grpc.pyi' -o -name '*_pb2.pyi' \) | while read -r file; do \
	  rel=$${file#$(OUT_PY)}; \
	  rel=$${rel#/}; \
	  moduledir=$$(dirname "$$rel"); \
	  prefix=$$(printf '%s' "$$moduledir" | tr '/' '.'); \
	  sed -i \
	    -e "s|^[[:space:]]*import[[:space:]]\+$$prefix\.\([[:alnum:]_]\+\)|from . import \1|" \
	    $$file; \
	  sed -i \
	    -e "s|^[[:space:]]*from[[:space:]]\+$$prefix\.\([[:alnum:]_]\+\)[[:space:]]\+import|from .\1 import|" \
	    $$file; \
	  sed -i -e "s|$$prefix\.\([[:alnum:]_]\+_pb2\)|\1|g" $$file; \
	  done
	@echo "Done."
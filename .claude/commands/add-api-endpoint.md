# /project:add-api-endpoint

Adds a new endpoint to an existing module. Use this when you already have a module scaffolded and want to add a specific new endpoint.

## Arguments
`$ARGUMENTS` — format: `<module> <method> <path>` (e.g. `friends POST /friends/bulk`)

## Steps

1. Parse the arguments into `module`, `method`, `path`

2. Open `civio-cloud/src/api/v1/${module}.py` and read the existing patterns

3. Add the endpoint:
   - Use existing dependencies (`get_current_user`, `get_db`, etc.)
   - Add request/response Pydantic schemas to `src/schemas/${module}.py`
   - Delegate business logic to the service layer; NEVER put logic in the router

4. Update the corresponding service method if this is a new business capability

5. Update `docs/03-api-contract.yaml`:
   - Add the path with method
   - Reference existing schemas or add new ones under `components/schemas`
   - Include example request/response

6. Add tests:
   - Unit test for any new service method in `tests/unit/services/test_${module}_service.py`
   - Integration test for the endpoint in `tests/integration/api/test_${module}.py`
   - At minimum: success case + auth failure + validation failure

7. Run contract test to verify the API matches the spec:
   ```bash
   cd civio-cloud
   poetry run schemathesis run ../docs/03-api-contract.yaml \
     --base-url http://localhost:8000 \
     --endpoint $path
   ```

8. Run full verification (same as `/project:scaffold-module` step 10)

9. Commit:
   ```
   feat(${module}): add ${method} ${path} endpoint
   ```

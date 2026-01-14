# TOON SDK

**Token-Oriented Object Notation** - A compact,
LLM-friendly format for defining data models and APIs with multi-language code generation.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![TypeScript](https://img.shields.io/badge/typescript-5.0+-blue.svg)](https://www.typescriptlang.org/)
[![PHP](https://img.shields.io/badge/php-8.1+-purple.svg)](https://www.php.net/)
[![Rust](https://img.shields.io/badge/rust-1.70+-orange.svg)](https://www.rust-lang.org/)

## Overview

TOON SDK enables you to define your data models, APIs, and configurations in a single, compact format that can be transformed into production-ready code for multiple languages and frameworks.

```yaml
@toon/2.0
name: MyAPI
version: 1.0.0

enum Status[active,inactive,pending]

model User{id,email,name,status}:
  id: uuid @primary @auto
  email: email @unique @index
  name: str @min(2) @max(100)
  status: Status = "active"

service UserService @base("/api/users"):
  list(page:int=1) -> [User] @GET
  get(id:uuid) -> User @GET("/{id}")
  create(data:CreateUser) -> User @POST @auth
```

**Generate code for any target:**
- **Python**: Pydantic models + FastAPI routes
- **TypeScript**: Zod schemas + Hono routes
- **PHP**: Laravel controllers + Eloquent models
- **Rust**: Serde structs + Axum handlers
- **OpenAPI**: Universal API specification

## Why TOON?

| Feature | TOON | OpenAPI | Pydantic | Prisma |
|---------|------|---------|----------|--------|
| Token efficient | ✅ ~70% less | ❌ Verbose | ❌ Python only | ❌ Schema only |
| Multi-language | ✅ 4+ languages | ⚠️ Codegen tools | ❌ Python | ❌ JS/TS |
| Models + APIs | ✅ Unified | ✅ APIs only | ✅ Models only | ✅ Models only |
| LLM-friendly | ✅ Designed for | ❌ Not designed | ❌ Code parsing | ❌ Not designed |
| Human-readable | ✅ Compact | ⚠️ YAML/JSON | ✅ Code | ✅ Schema |

## Quick Start

### Installation

**Python:**
```bash
pip install toon-sdk
```

**TypeScript/Node.js:**
```bash
npm install toon-sdk
```

**PHP:**
```bash
composer require softreck/toon-sdk
```

**Rust:**
```bash
cargo add toon-sdk
```

### Basic Usage

**1. Create a `.toon` file:**

```yaml toon
@toon/2.0
name: TodoAPI

enum Priority[low,medium,high,urgent]

model Todo{id,title,done,priority}:
  id: uuid @primary @auto
  title: str @min(1) @max(200)
  done: bool = false
  priority: Priority = "medium"

service TodoService @base("/api/todos"):
  list(done:bool?) -> [Todo] @GET
  get(id:uuid) -> Todo @GET("/{id}")
  create(title:str,priority:Priority?) -> Todo @POST
  toggle(id:uuid) -> Todo @POST("/{id}/toggle")
  delete(id:uuid) -> bool @DELETE("/{id}")
```

**2. Generate code:**

```bash
# Python (Pydantic)
toon generate todo.toon -t pydantic -o models.py

# Python (FastAPI)
toon generate todo.toon -t fastapi -o routes.py

# TypeScript (Zod)
toon generate todo.toon -t zod -o schemas.ts

# OpenAPI
toon generate todo.toon -t openapi -o openapi.json
```

## Syntax Reference

### Header & Metadata

```yaml toon
@toon/2.0
name: ProjectName
version: 1.0.0
author: Your Name
license: MIT
namespace: com.example
```

### Types

| Type | Description | Example |
|------|-------------|---------|
| `str` | String | `name: str` |
| `int` | Integer | `count: int` |
| `float` | Float/Decimal | `price: float` |
| `bool` | Boolean | `active: bool` |
| `date` | Date | `birthday: date` |
| `datetime` | DateTime | `created: datetime` |
| `uuid` | UUID | `id: uuid` |
| `email` | Email string | `email: email` |
| `url` | URL string | `website: url` |
| `json` | JSON object | `data: json` |
| `any` | Any type | `value: any` |
| `[T]` | Array of T | `tags: [str]` |
| `{K:V}` | Map K→V | `meta: {str:any}` |
| `T?` | Optional T | `bio: str?` |

### Enums

```yaml toon
// Simple enum
enum Status[active,inactive,pending]

// Enum with values
enum HttpCode{ok:200,not_found:404,error:500}
```

### Models

```yaml toon
// Full syntax
model User{id,email,name,role}:
  id: uuid @primary @auto
  email: email @unique @index
  name: str @min(2) @max(100)
  role: str = "user"

// Inline compact syntax
model Point{x:float,y:float,z:float=0}
model Money{amount:float,currency:str="USD"}
```

### Decorators

| Decorator | Description |
|-----------|-------------|
| `@primary` | Primary key |
| `@auto` | Auto-generated |
| `@unique` | Unique constraint |
| `@index` | Database index |
| `@foreign(Model.field)` | Foreign key |
| `@min(n)` | Minimum value/length |
| `@max(n)` | Maximum value/length |
| `@range(min,max)` | Value range |
| `@pattern("regex")` | Regex pattern |
| `@default(value)` | Default value |
| `@env("VAR")` | Environment variable |

### Services

```yaml toon
service UserService @base("/api/users") @auth:
  list(page:int=1,limit:int=20) -> [User] @GET
  get(id:uuid) -> User @GET("/{id}")
  create(data:CreateUser) -> User @POST
  update(id:uuid,data:UpdateUser) -> User @PUT("/{id}")
  delete(id:uuid) -> bool @DELETE("/{id}")
  
  // Custom endpoints
  search(q:str) -> [User] @GET("/search")
  activate(id:uuid) -> User @POST("/{id}/activate") @role(admin)
```

### Events

```yaml toon
event UserCreated{user_id,email,timestamp}:
  user_id: uuid
  email: email
  timestamp: datetime @auto

event OrderShipped{order_id,tracking_number}:
  order_id: uuid
  tracking_number: str
```

### Configuration

```yaml toon
config DatabaseConfig:
  url: str @env("DATABASE_URL") @required
  pool_size: int = 10 @env("DB_POOL_SIZE")
  timeout: int = 30

config AppConfig @extends(DatabaseConfig):
  debug: bool = false @env("DEBUG")
  port: int = 8000 @env("PORT")
```

## Language-Specific Usage

### Python

```python
from toon_sdk import ToonParser, PydanticGenerator, FastAPIGenerator

# Parse TOON file
parser = ToonParser()
schema = parser.parse_file("api.toon")

# Generate Pydantic models
pydantic_gen = PydanticGenerator()
models_code = pydantic_gen.generate(schema)

# Generate FastAPI routes
fastapi_gen = FastAPIGenerator()
routes_code = fastapi_gen.generate(schema)

# Or use decorators
from toon_sdk import toon_model, toon_service

@toon_model("User{id,name,email}")
class User:
    pass  # Fields auto-generated

@toon_service("UserService @base('/api/users')")
class UserService:
    pass  # Routes auto-generated
```

### TypeScript

```typescript
import { ToonParser, ZodGenerator, HonoGenerator } from 'toon-sdk';

// Parse TOON content
const parser = new ToonParser();
const schema = parser.parse(toonContent);

// Generate Zod schemas
const zodGen = new ZodGenerator();
const zodCode = zodGen.generate(schema);

// Generate Hono routes
const honoGen = new HonoGenerator();
const honoCode = honoGen.generate(schema);

// Runtime schema building
import { buildZodSchema } from 'toon-sdk';
const UserSchema = buildZodSchema(schema.models.find(m => m.name === 'User'));
```

### PHP

```php
use Toon\ToonParser;
use Toon\PhpGenerator;
use Toon\LaravelGenerator;

// Parse TOON file
$parser = new ToonParser();
$schema = $parser->parseFile('api.toon');

// Generate PHP classes
$phpGen = new PhpGenerator();
$phpCode = $phpGen->generate($schema);

// Generate Laravel controllers
$laravelGen = new LaravelGenerator();
$controller = $laravelGen->generateController($schema->services[0]);
$routes = $laravelGen->generateRoutes($schema);
```

### Rust

```rust
use toon_sdk::{ToonParser, RustGenerator};

fn main() -> Result<(), toon_sdk::ToonError> {
    // Parse TOON file
    let schema = toon_sdk::parse_toon_file("api.toon")?;
    
    // Generate Rust structs
    let rust_code = toon_sdk::generate_rust(&schema);
    
    // Access schema programmatically
    for model in &schema.models {
        println!("Model: {}", model.name);
    }
    
    Ok(())
}
```

## IDE Support

### VS Code Extension

Install from marketplace or manually:

```bash
cd vscode-extension
npm install
npm run compile
code --install-extension toon-language-*.vsix
```

Features:
- Syntax highlighting
- Code snippets
- Auto-completion
- Schema validation
- Generate commands

### JetBrains Plugin

Coming soon - syntax highlighting and code generation for IntelliJ, PyCharm, WebStorm, PHPStorm.

## Examples

See the `examples/` directory:

- `blog-api.toon` - Simple blog with posts and comments
- `ecommerce-api.toon` - Full e-commerce with products, orders, payments

## API Reference

### ToonSchema Structure

```typescript
interface ToonSchema {
  header: { version: string };
  metadata: Record<string, string>;
  enums: ToonEnum[];
  models: ToonModel[];
  services: ToonService[];
  events: ToonEvent[];
  configs: ToonConfig[];
  validators: ToonValidator[];
}
```

### CLI Commands

```bash
# Parse and validate
toon validate schema.toon

# Generate code
toon generate schema.toon -t <target> -o <output>

# Available targets:
#   pydantic, fastapi, dataclasses (Python)
#   zod, io-ts, hono (TypeScript)
#   php, laravel (PHP)
#   rust, serde (Rust)
#   openapi, jsonschema (Specs)

# Export to JSON
toon export schema.toon -o schema.json
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

## License

Apache 2 License - see [LICENSE](LICENSE) for details.

## Links

- [Specification](spec/TOON-SPEC.md)
- [JSON Schema](schemas/toon-v2.schema.json)
- [GitHub Repository](https://github.com/softreck/toon-sdk)
- [Documentation](https://toon-sdk.dev)

---

Built with ❤️ by [Softreck](https://softreck.com)

# TOON (Token-Oriented Object Notation) Specification v2.0

## Overview

TOON is a compact, LLM-friendly notation format for defining:
- **Data Models** (like Pydantic/Zod)
- **Service Configurations** (like OpenAPI)  
- **Multi-platform Code Generation**
- **API Contracts**

## Design Principles

1. **Compact** - Minimal tokens for LLM processing
2. **Readable** - Human-friendly with syntax highlighting
3. **Validatable** - JSON Schema compatible
4. **Polyglot** - Multi-language code generation
5. **Complementary** - Works with existing tools (Pydantic, Zod, OpenAPI)

---

## Basic Syntax

### Header Block
```yaml toon
@toon/2.0
name: MyProject
version: 1.0.0
author: developer@example.com
license: MIT
```

### Type Definitions

#### Primitive Types
```yaml toon
types:
  # Built-in primitives
  str, int, float, bool, date, datetime, uuid, email, url, json
  
  # Optional types use ?
  optional_str: str?
  
  # Arrays use []
  tags: [str]
  
  # Maps use {}
  metadata: {str:any}
```

#### Custom Types (Models)
```yaml toon
model User{id,name,email,role}:
  id: uuid @primary @auto
  name: str @min(2) @max(100)
  email: email @unique @index
  role: Role = "user"
  created_at: datetime @auto
  profile: Profile?
  tags: [str] = []

model Profile{bio,avatar,social}:
  bio: str? @max(500)
  avatar: url?
  social: {str:url}
```

### Compact Model Notation
```toon
# Full definition
model Product{name,price,stock}:
  name: str @required
  price: float @min(0)
  stock: int = 0

# Compact inline (for simple models)
model Point{x:float,y:float,z:float=0}
model Color{r:int,g:int,b:int,a:float=1.0}
```

---

## Enums and Constants

```yaml toon
enum Role[admin,moderator,user,guest]
enum Status[pending,active,suspended,deleted]

# With values
enum HttpCode{ok:200,created:201,bad_request:400,not_found:404,server_error:500}

# Constants
const MAX_ITEMS: int = 1000
const API_VERSION: str = "v2"
const RATE_LIMITS: {str:int} = {free:100,pro:1000,enterprise:10000}
```

---

## Services Definition

### Basic Service
```yaml toon
service UserService @base("/api/users"):
  # Methods with signatures
  list(page:int=1,limit:int=20) -> [User] @GET @cache(60)
  get(id:uuid) -> User @GET("/{id}") @auth
  create(data:CreateUser) -> User @POST @auth @role(admin)
  update(id:uuid,data:UpdateUser) -> User @PUT("/{id}") @auth
  delete(id:uuid) -> bool @DELETE("/{id}") @auth @role(admin)
  
  # Custom endpoints
  search(query:str,filters:SearchFilters?) -> SearchResult @GET("/search")
  bulk_create(items:[CreateUser]) -> [User] @POST("/bulk") @auth @role(admin)
```

### Service with Middleware
```yaml toon
service ProductService @base("/api/products") @middleware(auth,logging,ratelimit):
  list(category:str?,page:int=1) -> PaginatedProducts @GET @cache(300)
  get(id:uuid) -> Product @GET("/{id}")
  create(data:CreateProduct) -> Product @POST @validate
  
  # Async operations
  import_csv(file:upload) -> ImportJob @POST("/import") @async
  export(format:str="csv") -> download @GET("/export") @async
```

---

## API Contracts

### Request/Response Models
```yaml toon
# Input models (for creation/updates)
input CreateUser{name,email,password}:
  name: str @min(2) @max(100)
  email: email
  password: str @min(8) @pattern("^(?=.*[A-Za-z])(?=.*\\d)")

input UpdateUser{name?,email?,role?}:
  name: str? @min(2) @max(100)
  email: email?
  role: Role?

# Output models (for responses)
output UserResponse{id,name,email,role,created_at}:
  id: uuid
  name: str
  email: email
  role: Role
  created_at: datetime

# Paginated response
output PaginatedUsers{items,total,page,pages}:
  items: [UserResponse]
  total: int
  page: int
  pages: int
```

### Error Definitions
```yaml toon
error ValidationError{field,message,code}:
  field: str
  message: str
  code: str = "validation_error"

error NotFoundError{resource,id}:
  resource: str
  id: str
  code: str = "not_found"

errors UserService:
  create: [ValidationError, DuplicateEmailError]
  get: [NotFoundError]
  delete: [NotFoundError, PermissionDeniedError]
```

---

## Validators and Decorators

### Built-in Validators
```yaml toon
@required          # Field is required
@optional          # Field is optional (same as ?)
@min(n)            # Minimum value/length
@max(n)            # Maximum value/length
@range(min,max)    # Value range
@pattern(regex)    # Regex pattern
@email             # Valid email
@url               # Valid URL
@uuid              # Valid UUID
@unique            # Unique constraint
@index             # Database index
@primary           # Primary key
@auto              # Auto-generated
@default(value)    # Default value
@deprecated(msg)   # Deprecated field
```

### Custom Validators
```yaml toon
validator PositiveNumber:
  check: value > 0
  message: "Must be positive"

validator ValidNIP:
  check: validate_nip(value)
  message: "Invalid Polish NIP number"

model Company{nip:str @ValidNIP}
```

---

## Events and Messaging

```yaml toon
event UserCreated{user_id,email,timestamp}:
  user_id: uuid
  email: email
  timestamp: datetime @auto

event OrderPlaced{order_id,user_id,total,items}:
  order_id: uuid
  user_id: uuid
  total: float
  items: [OrderItem]

channel notifications @broker(rabbitmq):
  publish: [UserCreated, OrderPlaced, PaymentReceived]
  subscribe: [EmailNotification, PushNotification]

channel analytics @broker(kafka):
  publish: [UserCreated, OrderPlaced, PageView]
  partitions: 6
  retention: 7d
```

---

## Database Mappings

```yaml toon
database postgres @connection("DATABASE_URL"):
  table users -> User:
    id @primary @uuid_generate_v4
    email @unique @index
    created_at @default(now())
    
  table products -> Product:
    id @primary @serial
    category @index
    price @check(price > 0)
    
  # Relations
  relation users.orders -> Order[] @foreign(user_id)
  relation orders.items -> OrderItem[] @foreign(order_id)
```

---

## Configuration Blocks

```yaml toon
config development:
  database: postgres://localhost/dev
  cache: redis://localhost:6379
  debug: true
  log_level: debug

config production:
  database: ${DATABASE_URL}
  cache: ${REDIS_URL}
  debug: false
  log_level: warn
  
config testing @extends(development):
  database: postgres://localhost/test
  mock_external: true
```

---

## Imports and Modules

```yaml toon
# Import from other TOON files
import "./auth.toon" as auth
import "./common/pagination.toon" use {Paginated, PageInfo}
import "./validators.toon" use *

# Use imported definitions
model Post{author:auth.User,content,pagination:Paginated}
```

---

## Full Example

```yaml toon
@toon/2.0
name: EcommerceAPI
version: 2.1.0
description: E-commerce platform API definition

# Types and Enums
enum OrderStatus[pending,processing,shipped,delivered,cancelled]
enum PaymentMethod[card,paypal,bank_transfer,crypto]

# Models
model User{id,email,name,role,orders}:
  id: uuid @primary @auto
  email: email @unique @index
  name: str @min(2) @max(100)
  role: str = "customer"
  orders: [Order]?
  created_at: datetime @auto

model Product{id,name,price,stock,category}:
  id: uuid @primary @auto
  name: str @min(1) @max(200)
  description: str? @max(2000)
  price: float @min(0)
  stock: int @min(0) = 0
  category: str @index
  images: [url] = []

model Order{id,user_id,items,status,total}:
  id: uuid @primary @auto
  user_id: uuid @foreign(User.id)
  items: [OrderItem]
  status: OrderStatus = "pending"
  total: float @min(0)
  payment_method: PaymentMethod?
  created_at: datetime @auto

model OrderItem{product_id,quantity,price}:
  product_id: uuid @foreign(Product.id)
  quantity: int @min(1)
  price: float @min(0)

# Input/Output
input CreateOrder{items:[{product_id:uuid,quantity:int}],payment_method:PaymentMethod}
output OrderResponse{id,status,total,items,created_at}

# Services
service ProductService @base("/api/products"):
  list(category:str?,page:int=1,limit:int=20) -> Paginated[Product] @GET
  get(id:uuid) -> Product @GET("/{id}")
  create(data:CreateProduct) -> Product @POST @auth @role(admin)
  update(id:uuid,data:UpdateProduct) -> Product @PUT("/{id}") @auth @role(admin)
  delete(id:uuid) -> bool @DELETE("/{id}") @auth @role(admin)

service OrderService @base("/api/orders") @auth:
  list(status:OrderStatus?,page:int=1) -> Paginated[Order] @GET
  get(id:uuid) -> OrderResponse @GET("/{id}")
  create(data:CreateOrder) -> OrderResponse @POST
  cancel(id:uuid) -> OrderResponse @POST("/{id}/cancel")

# Events
event OrderPlaced{order_id,user_id,total}
event PaymentReceived{order_id,amount,method}
event OrderShipped{order_id,tracking_number}

# Config
config:
  pagination_default: 20
  pagination_max: 100
  cache_ttl: 300
```

---

## Code Generation Targets

TOON can generate code for:

| Target | Models | Services | Validation |
|--------|--------|----------|------------|
| Python (Pydantic) | ✅ | ✅ (FastAPI) | ✅ |
| TypeScript (Zod) | ✅ | ✅ (Express/Hono) | ✅ |
| PHP | ✅ | ✅ (Laravel/Symfony) | ✅ |
| Rust (Serde) | ✅ | ✅ (Axum/Actix) | ✅ |
| Node.js | ✅ | ✅ (Express/Fastify) | ✅ |
| OpenAPI 3.1 | ✅ | ✅ | ✅ |
| JSON Schema | ✅ | - | ✅ |
| GraphQL | ✅ | ✅ | ✅ |
| Protobuf | ✅ | ✅ | - |

---

## File Extensions

- `.toon` - Standard TOON files
- `.toon.json` - JSON representation (for tooling)
- `.toon.yaml` - YAML representation (alternative)

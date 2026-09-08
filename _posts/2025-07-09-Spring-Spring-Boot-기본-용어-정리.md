---
title: "[Spring] Spring Boot 기본 용어 정리"
date: 2025-07-09 19:50:53 +0900
last_modified_at: 2026-09-08 09:39:19 +0900
render_with_liquid: false
---
> 💡 이 게시글은 강의를 수강하며 학습한 내용을 중요한 키워드 중심으로 정리한 개인 학습 기록입니다. 오직 기억 복기를 위한 목적으로 작성되었으며, 모든 내용을 포함하지 않으므로 학습 자료로는 적합하지 않습니다.

> 2025.07.03 ~
멋쟁이사자처럼 세션 중 DTO, 연관관계 파트 이해하기 어려워 개인학습.
데이터베이스 미수강 상태. 중구난방한 개념정리.

# REST API
`API` Application Programming Interface
- 응용 프로그램에서 사용할 수 있도록 다른 응용 프로그램을 제어할 수 있게 만든 인터페이스.

`REST` Representational State Transfer
- 자원(DATA)의 이름으로 구분하여 해당 자원의 상태를 교환하는 것을 의미.
- HTTP URI 를 통해 자원을 명시하고 HTTP Method (Create, Read, Update, Delete) 를 통해 자원을 교환하는 것.

`REST API` REST 아키텍처의 조건을 준수하는 어플리케이션 프로그래밍 인터페이스
- Rest 기반으로 시스템을 분산하여 확장성과 재사용성을 높임

# Spring Annotation 정리
![](/assets/img/velog/dbf10a73-b92c-48ca-8964-642ef5cdc591/64e0072300e7f3ff74efe65003073a9c444a6fe2d45b7fc25593bc442b963c9a.png)

## ☑️ Get API
**@RestController**
`@RestController` @Controller 에 @ResponseBody 가 결합된 어노테이션.

**@RequestMapping**
`@RequestMapping` URL을 매핑하여 경로를 설정하여 해당 메소드에서 처리.

![](/assets/img/velog/dbf10a73-b92c-48ca-8964-642ef5cdc591/764d0fa43faa8451b718e25bd792ef96e72f5b8b15e106c62546e6ec176e267f.png)

⬆️ 고전적인 방식

**@GetMapping**
`@GetMapping` 별도의 파라미터 없이 GET API 호출하는 경우 사용되는 방법.

**@PathVariable**
`
@PathVariable` GET 형식의 요청에서 파라미터를 전달하기 위해 URL에 값을 담아 요청하는 방법.
아래 방식은 {변수} 의 이름과 메소드의 매개변수와 일치시켜야함.
```java
@GetMapping(value = "/variable1/{variable}")
public String getVariable1(@PathVariable String variable) {
    return variable;
}
```
```java
// http://localhost:8080/api/v1/get-api/variable1/{String 값}
@GetMapping(value = "/variable2/{variable}")
public String getVariable2(@PathVariable("variable") String var) {
    return var;
}
```
**@RequestParam**
`@RequestParam` GET 형식의 요청에서 쿼리 문자열을 전달하기 위해 사용되는 방법
'?' 를 기준으로 우측에 {키}={값} 의 형태로 전달되며, 복수 형태로 전달할 경우 & 를 사용함. 
```
http://localhost:8080/api/v1/get-api/request1?name=flature&email=thinkground.flature@gmail.com&organization=thinkground
```
```java
@GetMapping(value = "/request1")
public String getRequestParam1(
        @RequestParam String name,
        @RequestParam String email,
        @RequestParam String organization) {
    return name + " " + email + " " + organization;
}
```
⬇️ 이 코드는 쿼리 파라미터가 몇 개가 들어올지 모를 때 전부 받아 처리하는 예시입니다.
````
http://localhost:8080/api/v1/get-api/request2?name=flature&email=thinkground.flature@gmail.com&organization=thinkground
`````
````java
@GetMapping(value = "/request2")
public String getRequestParam2(@RequestParam Map<String, String> param) {
    StringBuilder sb = new StringBuilder();

    param.entrySet().forEach(map -> {
        sb.append(map.getKey() + " : " + map.getValue() + "\n");
    });

    return sb.toString();
}
````

## ☑️ Post API 
리소스를 추가하기 위해 사용되는 API
**@PostMapping**
`@PostMapping` POST API 를 제작하기 위해 사용되는 어노테이션
일반적으로 추가하고자 하는 Resource 를 http body에 추가하여 서버에 요청
→ 그렇기 때문에 **@RequestBody**를 이용하여 body에 담겨있는 값을 받아야함.

```java
@PostMapping("/member1")
public class PostController {
    // http://localhost:8080/api/v1/post-api/member
    public String postMember(@RequestBody Map<String, Object> postData) {
        StringBuilder sb = new StringBuilder();

        postData.entrySet().forEach(map -> {
                sb.append(map.getKey() + " : " + map.getValue() + "\n");
        });
        return sb.toString();
    }
````
```java
@PostMapping(value = "/member2")
public String postMemberDto(@RequestBody MemberDTO memberDTO) {
    return memberDTO.toString();
}
````

### 🔗 GET ↔ POST 요청의 차이
![](/assets/img/velog/dbf10a73-b92c-48ca-8964-642ef5cdc591/de9ff18fa2079c3d0542e0cc299b18d93aa0f54aedd730be9e7d3b4e47a621fa.png)

🔹 GET은 데이터를 URL(주소)에 붙여서 전송
```
GET /api/user?name=minjun&email=test@gmail.com
```
→ @RequestParam, @PathVariable로 처리하는 게 기본 방식

🔹 POST는 데이터를 주소에 안 붙이고, HTTP Body에 담아서 전송.
```
POST /api/user
Content-Type: application/json

{ "name": "minjun", "email": "test@gmail.com" }
```
이 Body 데이터를 자바 객체로 변환해주는 게 바로 @RequestBody
```java
@PostMapping("/user")
public String createUser(@RequestBody UserDTO user) {
    return user.getName();
}
```
## ☑️ Put API
해당 리소스가 존재하면 갱신하고, 리소스가 없을 경우에는 새로 생성해주는 API
업데이트를 위한 메서드.
기본적인 동작 방식은 Post API 와 동일.


## ☑️ Delete API
서버를 통해 리소스를 삭제 하기 위해 사용되는 API.
일반적으로 **@PathVaraible** 을 통해 리소스 ID 를 받아 처리.

# Lombok
반복되는 메서드를 annotation 을 사용하여 자동으로 작성해주는 라이브러리.
일반적으로 VO, DTO, Model, Entity 등의 데이터 클래스에서 주로 사용됨.

`@Getter`
`@Setter`
`@NoArgsContructor` 파라미터가 없는 생성자를 생성
`@AllArgsConstructor` 모든 필드값을 파라미터로 갖는 생성자를 생성
`@RequiredArgsConstructor` 필드값 중 final 이나 @NotNull인 값을 갖는 생성자를 생성
`@ToString` toString 메서드를 자동으로 생성해주는 기능

이외에도 다른 에노테이션이 많지만 생략.

# DTO, DAO, Repository, Entity
![](/assets/img/velog/dbf10a73-b92c-48ca-8964-642ef5cdc591/58df5f3fbe098be6a3083d8ce7d3256db9a5b7b1652baf0d3e42b94553ee1f99.png)

![](/assets/img/velog/dbf10a73-b92c-48ca-8964-642ef5cdc591/9830874fe78a3f804fc0b3736b348e7b08fad65c9b152e048ca7b07dd49fd0f9.png)

## ☑️ Entity
데이터베이스에 쓰일 컬럼과 여러 엔티티 간의 연관관계를 정의
데이터베이스의 테이블을 하나의 엔티티로 생각해도 무방함
실제 데이터베이스와 1:1 로 매핑됨

## ☑️ Repository
Entity 에 의해 생성된 데이터베이스에 접근하는 메서드를 사용하기 위한 인터페이스
Service 와 DB 를 연결하는 고리의 역할을 수행
**데이터베이스에 적용하고자 하는 CRUD 를 정의하는 영역**

## ☑️ DAO (Data Access Object)
**데이터베이스에 접근하는 객체**를 의미
Service 가 DB 에 연결할 수 있게 해주는 역할
**DB 를 사용하여 데이터를 조회하거나 조작하는 기능을 전담**

- DAO는 Repository보다 더 기술적으로 유연하게 커스터마이징하고 싶을 때 쓰는 계층.
- DAO는 “정말 복잡한 쿼리 작업을 따로 떼고 싶다” 싶을 때 쓰는 확장 계층.

① 간단한 구조
```
Client → Controller → Service → Repository → DB
```
DB 접근은 JpaRepository로 직접

② DAO를 따로 둔 구조 (복잡한 로직 분리용)
```
Client → Controller → Service → DAO → Repository → DB
```
DAO는 복잡한 DB 쿼리, 조건 등을 분리해서 담당
Service는 업무 흐름만 담당
이 구조는 MyBatis, JDBC 등에서 특히 유용함

## ☑️ DTO (Data transfer Object)

DTO 는 VO(Value Object)로 불리기도 하며, **계층간 데이터 교환을 위한 객체를 의미**
VO 의 경우 Read Only 의 개념을 가지고 있음


## ☑️ toEntity(), toDto()

toEntity()와 toDto()는 DTO ↔ Entity 간의 변환을 담당하는 메서드

![](/assets/img/velog/dbf10a73-b92c-48ca-8964-642ef5cdc591/2722725985ccb10a5985c8b31dd2a0701524414ef7b7ab4804e733ce8f63ff92.png)

![](/assets/img/velog/dbf10a73-b92c-48ca-8964-642ef5cdc591/90f42e1a33df7ccf96396594056def49fcc63d4b4e0af32bb7cec6455bef480c.png)

```java
public ProductEntity toEntity() {
    return ProductEntity.builder()
  		.productName("제로콜라")  // 값 넣고
  		.productPrice(1800)       // 또 넣고
  		.productStock(10)         // 또 넣고
  		.build();                 // 이제 조립 완료 → 객체 생성
}
```
`Builder`는 “필드를 하나씩 지정해가면서, 마지막에 .build()로 객체를 만드는 방식”
`.필드명()` 필드를 하나씩 설정 (Builder 내부에 저장)
`.build()` 그동안 저장한 값으로 진짜 ProductEntity 객체를 생성

DTO → Entity 변환 코드엔 id가 없어도 @GeneratedValue를 사용 중이라면,
id는 DB가 자동으로 만들어주기 때문에 DTO에서 따로 넣지 않아도 됨
```java
@Id
@GeneratedValue(strategy = GenerationType.IDENTITY)
private Long id;
```
`@GeneratedValue`: 값을 자동 생성하라는 의미
`IDENTITY`: DB가 자동 증가 시켜주는 방식 (MySQL의 AUTO_INCREMENT처럼)


```
[ProductDto]                   [ProductEntityBuilder]             [ProductEntity]
------------------            ------------------------           -------------------
productName = "아메리카노"  →  .productName("아메리카노")     →  생성된 진짜 객체
productPrice = 3500        →  .productPrice(3500)           →  build()로 완성
productStock = 50          →  .productStock(50)
                             →  .build() 호출 → 객체 리턴

```

이 메서드들은 일반적으로 **“매핑 메서드(mapping method)”**,
또는 **“객체 변환 메서드(object conversion method)”**라고 한다.

# ORM (Object Relational Mapping)
어플리케이션의 객체와 관계형 데이터베이스의 데이터를 자동으로 매핑해주는 것을 의미

Java의 데이터 클래스와 관계형 데이터베이스의 테이블을 매핑

객체지향 프로그래밍과 관계형 데이터베이스의 차이로 발생하는 제약사항을 해결해주는 역할을 수행

# Spring Data Jpa
Spring Framework 에서 JPA를 편리하게 사용할 수 있게 지원하는 라이브러리 
- CRUD 처리용 인터페이스 제공
- Repository 개발 시 인터페이스만 작성하면 구현 객체를 동적으로 생성해서 주입
- 데이터 접근 계층 개발시 인터페이스만 작성해도 됨

Hibernate 에서 자주 사용되는 기능을 조금 더 쉽게 사용할 수 있게 구현한 것

# 유효성 검사 / 데이터 검증 (Validation)

서비스의 비즈니스 로직이 올바르게 동작하기 위해 사용되는 데이터에 대한 사전 검증하는 작업이 필요함

유효성 검사 혹은 데이터 검증이라고 부르는데, 흔히 `Validation` 이라고 부름

`Validation` 은 들어오는 데이터에 대해 의도한 형식의 값이 제대로 들어오는지 체크하는 과정을 뜻함

`Bean Validation`

![](/assets/img/velog/dbf10a73-b92c-48ca-8964-642ef5cdc591/2f9c4a703dc975fa37add740a6584cde38af823d4da8463169e936b363df3e98.png)

# Exception

```
📦 Java 예외 클래스 구조

java.lang.Object
└── Throwable                             ← 던질 수 있는 모든 예외의 조상
    ├── Error                             ← 시스템 치명적 오류 (개발자가 잡지 않음)
    │   ├── OutOfMemoryError              ← 메모리 부족
    │   └── StackOverflowError            ← 무한 재귀 호출
    │   ...
    └── Exception                         ← 개발자가 처리해야 할 예외
        ├── IOException                   ← Checked Exception: 파일, 네트워크
        │   ├── FileNotFoundException     ← 파일 없거나 권한 없음
        │   └── EOFException              ← 파일 끝 도달
        │   ...
        └── RuntimeException              ← Unchecked Exception: 개발자 실수
            ├── NullPointerException      ← null 값 접근
            ├── IndexOutOfBoundsException ← 배열, 리스트 인덱스 초과
            ├── IllegalArgumentException  ← 잘못된 메서드 인자 전달
            ├── NumberFormatException     ← 문자열 → 숫자 변환 실패
            └── 사용자 정의 예외들          ← ex. InvalidStatusException 등

✅ Checked Exception
- 컴파일 시점에 처리 강제됨 (try-catch or throws)
- 대부분 외부 환경 문제 (파일, DB, 네트워크 등)
- 예시:
  - IOException
  - SQLException
  - ParseException

⚠️ Unchecked Exception
- 컴파일러가 처리 강제하지 않음 (선택적으로 try-catch)
- 대부분 개발자 실수 or 로직 오류
- 예시:
  - NullPointerException
  - IllegalArgumentException
  - IndexOutOfBoundsException

🔥 Error
- JVM 자체 오류 → 복구 불가, try-catch로 잡지 말 것
- 예시:
  - OutOfMemoryError
  - StackOverflowError

🧠 실무 기준 정리 (언제, 어디서 처리?)

상황                      | 예외 타입   | 예외 클래스 예시           | 처리 위치
--------------------------|------------|----------------------------|-----------------------------
파일이 없음               | Checked    | FileNotFoundException      | try-catch or throws
DB 연결 실패              | Checked    | SQLException               | throws or ControllerAdvice
사용자 입력이 null        | Unchecked  | NullPointerException       | Service 단에서 조건문
파라미터 유효성 실패      | Unchecked  | IllegalArgumentException   | Service or Validator
비즈니스 상태 이상        | Unchecked  | InvalidStatusException     | 커스텀 예외 만들어 throw
시스템 메모리 부족        | Error      | OutOfMemoryError           | X (복구 불가, JVM 종료)

🎯 핵심 정리 문장

- Checked Exception → 외부 환경 문제니까 꼭 try-catch or throws 하라고 컴파일러가 강제함
- Unchecked Exception → 개발자가 실수한 로직 문제라 컴파일러는 강제 안 함 (선택적 처리)
- Error → 시스템 문제라서 잡는 게 아니라 그냥 죽는 게 맞음
```

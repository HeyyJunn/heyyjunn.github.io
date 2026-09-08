---
title: "[Spring] 내가 보려고 만든 MVC 기초흐름도"
date: 2025-05-06 16:12:07 +0900
last_modified_at: 2026-09-08 10:12:48 +0900
thumbnail:
  path: "/assets/img/velog/ca010783-034c-45e4-9551-5aecfa373dbe/35b03ad997434e0fd86975a7d1f2b256329ca4fe3b1b6e481d1b7454d2f1bf9a.jpg"
  alt: "[Spring] 내가 보려고 만든 MVC 기초흐름도"
render_with_liquid: false
---
>별거 없습니다.
그저 MVC 의 개념/흐름이 너무 추상적이라 gpt를 통한 시각화로 정리해봤어요. 스프링 어려워 ㅠㅠ.

# MVC
MVC는 Model, View, Controller의 약자로, 웹 요청 처리 과정을 역할별로 나눈 아키텍처 패턴.

✅ MVC를 왜 쓰는가? (핵심 목적)
◼︎ 역할을 분리해서 **관심사의 분리(Separation of Concerns)**를 달성
→ 유지보수, 테스트, 확장성이 매우 쉬워짐
예: 디자이너는 View만 바꾸면 되고, 개발자는 Controller나 Model만 다루면 됨

✅ MVC 흐름 예시
⏵ 1.	`Controller`: “/members 요청을 받았어! → Service에서 회원 목록 가져올게!”
⏵ 2.	`Model`: “여기 회원 데이터 리스트야.”
⏵ 3.	`View`: “이 데이터를 HTML에 예쁘게 표시할게!”



`Model` 애플리케이션의 핵심 데이터, 비즈니스 로직 포함 (데이터를 담는 객체는 보통 DB와 연결된 정보.) 

- 데이터를 처리하는 영역
- 데이터베이스와 연동을 위한 DAO(Data Access Object) 와 데이터의 구조를 표현하는 DO(Data Object)로 구성됨.

✔ Service는 Model에 포함되며, 비즈니스 로직(예: 중복회원 검사 등)을 처리함
✔ Repository도 Model에 포함되며, DB 접근 로직을 담당함
✔ domain 폴더는 Model 안의 ‘도메인 객체들’이 위치하는 공간
✔ MVC에서 “Model”은 단순히 “데이터”만 의미하는 게 아니고, 비즈니스 로직 전체를 포함한 데이터 처리 계층 전체를 의미

	예시클래스/에노테이션 - Member, MemberRepository, MemberService

`View` 사용자에게 보여지는 화면 (HTML)
	
    예시클래스/에노테이션 - createMemberForm.html, memberList.html

`Controller` 사용자 입력을 받아 처리하고, 결과를 View에 전달

- **모델(Model) 과 뷰(View) 사이에서 브릿지 역할을 수행**
- 앱의 사용자로부터 입력에 대한 응답으로 모델 및 뷰를 업데이트 하는 로직을 포함
- 사용자의 요청은 모두 컨트롤러를 통해 진행되어야 함
- 컨트롤러로 들어온 요청은 어떻게 처리할지 결정하여 모델로 요청을 전달함

```
예시클래스/에노테이션 - MemberController, @Controller, @GetMapping, @PostMapping
```
    
    
![](/assets/img/velog/ca010783-034c-45e4-9551-5aecfa373dbe/9b48ebcee8ac5cbd68efc4c317e5a26b34b69aa2b34c2588389f7bbcb00926cd.png)

    
```
┌─────────────┬────────────────────────────┐
│   계층       │      Spring 클래스 예시   	   │
├─────────────┼────────────────────────────┤
│ Controller  │ @Controller                │
│             │ MemberController           │
├─────────────┼────────────────────────────┤
│ Model       │ @Service                   │
│             │ MemberService              │
│             │                            │
│             │ @Repository                │
│             │ MemberRepository           │
│             │                            │
│             │ Domain 객체                 │
│             │ Member                     │
├─────────────┼────────────────────────────┤
│ View        │ HTML, Thymeleaf 템플릿       │
│             │ createMemberForm.html 등    │
└─────────────┴────────────────────────────┘
````


```
📦 Model 계층 – 핵심 데이터 + 로직
├── Domain 객체: 순수 데이터 구조
│   └── Member.java
│       - 필드: id, name
│       - 역할: 회원이라는 데이터를 표현
│
├── Repository 계층: DB 접근 책임
│   ├── MemberRepository.java (interface)
│   └── MemoryMemberRepository.java (implements)
│       - save(), findById(), findAll(), findByName() 메서드 포함
│       - 현재는 메모리에 저장, 나중엔 DB로 교체 가능
│
└── Service 계층: 비즈니스 로직 처리
    └── MemberService.java
        - join(): 회원가입 로직
        - findMembers(): 회원 목록 조회
        - validateDuplicateMember(): 중복 회원 검사
        
🧭 Controller 계층 – 사용자 요청 처리
└── MemberController.java
    - @Controller
    - GET /members/new → 회원가입 HTML 폼 리턴
    - POST /members/new → form 데이터 받아서 회원 등록
    - GET /members → 회원 목록 조회

    => 역할: 사용자의 HTTP 요청을 받고, 필요한 로직(MemberService)을 호출하고,
             최종 결과(View 이름)를 리턴함

👀 View 계층 – 화면 출력 담당 (HTML 파일들)
└── Thymeleaf 템플릿
    ├── home.html
    ├── createMemberForm.html
    └── memberList.html

    => 역할: Controller가 넘겨준 데이터를 화면에 보여주는 역할.
             사용자는 이 화면만 보게 됨.
```
![](/assets/img/velog/ca010783-034c-45e4-9551-5aecfa373dbe/17078a10b7e0659123ac212200ffc31f4efa751df7e34c44bc5e91837d2ed839.png)

![](/assets/img/velog/ca010783-034c-45e4-9551-5aecfa373dbe/80279cb3170df1885a9ab31cea835b3eedaa5be3b48640a5b31eef6c06dbc7dd.png)


# Spring MVC 요청 처리 전체 흐름 정리 (Step 1~8)
```
⏵ [Step 1] 브라우저가 URL 요청 (예: /members)
↓
※ MVC: 없음 (사용자 → 서버 요청)
※ 사용된 요소: HTTP 요청 (GET /members)

⏵ [Step 2] DispatcherServlet이 요청을 받음
↓
※ MVC: Controller의 입구 역할
※ 클래스: DispatcherServlet (Spring이 자동 등록)

⏵ [Step 3] HandlerMapping이 어떤 컨트롤러(핸들러)를 쓸지 결정
↓
※ MVC: Controller 결정
※ 관련 애노테이션: @Controller, @GetMapping("/members")
※ 관련 클래스: MemberController.java

⏵ [Step 4] HandlerAdapter가 해당 컨트롤러를 실행할 방법 결정
↓
※ MVC: Controller 실행기
※ 클래스: RequestMappingHandlerAdapter
※ 내부 동작: handle(handler) 호출 → controller 실행

⏵ [Step 5] Controller가 실행되고, model에 데이터 담고 view 이름 리턴
↓
※ MVC: Controller
※ 코드 예:
   model.addAttribute("members", 리스트)
   return "members/memberList"
※ 반환값: ModelAndView("members/memberList", model)

⏵ [Step 6] ViewResolver가 View 이름 → HTML 파일 경로로 변환
↓
※ MVC: View 결정
※ 예: "members/memberList" → /templates/members/memberList.html
※ 설정: prefix="/templates/", suffix=".html"

⏵ [Step 7] View 객체가 model 데이터를 끼워 넣고 HTML 생성
↓
※ MVC: View
※ 템플릿 엔진: Thymeleaf
※ HTML 예시:
   <tr th:each="member : ${members}">
     <td th:text="${member.name}"></td>
   </tr>
   
⏵ [Step 8] DispatcherServlet이 최종 HTML을 브라우저에 응답
↓
※ MVC: 없음 (출력 단계)
※ 최종 출력: 완성된 HTML이 사용자 브라우저에 도착
```
**📌 Step 1. 핸들러 조회 (HandlerMapping 동작)**
1. `DispatcherServlet`이 들어온 요청(URL)을 보고
2. `HandlerMapping`에게 "이 URL 처리할 수 있는 컨트롤러 있어?" 물어봄
```
- GET /members 요청이 들어왔다면,
@GetMapping("/members") 라고 적힌 메서드를 가진 Controller가 Handler
HandlerMapping은 미리 스프링이 등록해둔 URL → 핸들러 목록을 가지고 있음

즉, Handler = 컨트롤러라고 생각해도 거의 일치
```
**📌 Step 2. 핸들러 어댑터 조회 (HandlerAdapter)**
3. `Handler`를 찾았으면, `DispatcherServlet`은 이제 "얘를 실행시킬 방법"을 찾아야 함
4. 그래서 `HandlerAdapter` 목록을 뒤져서,
   이 `Handler`를 실행할 수 있는 `HandlerAdapter`를 찾아냄
```
HandlerAdapter는 Handler(컨트롤러)를 실행시키는 객체.
인터페이스이고, 다양한 구현체들이 있음.

Handler는 다양한 타입일 수 있음. (예: @Controller, @RestController, HttpRequestHandler, SimpleController 등)

❓ “나는 @RequestMapping을 쓰지 않고 @GetMapping만 썼는데, 어떻게 요청이 처리된 거야?”
	- @GetMapping, @PostMapping은 사실 @RequestMapping의 “축약 버전”.
    내부적으로는 결국 다 @RequestMapping으로 변환돼서 동작.

그래서 Controller를 실행하는 방법이 각각 다를 수 있음!
-> 그래서 그걸 감싸주는 게 HandlerAdapter

예: RequestMappingHandlerAdapter는 @RequestMapping이 붙은 메서드를 실행할 수 있음.

```
**📌 Step 3~4. 핸들러 어댑터가 핸들러 실행 (Controller 실행)**
5. 찾은 `HandlerAdapter`가 `핸들러(=Controller)`를 실행함
6. `Controller` 내부의 로직을 처리함
7. **return 값**으로 `ModelAndView`를 `DispatcherServlet`에게 줌

````java
@GetMapping("/members")
public String list(Model model) {
    List<Member> members = memberService.findMembers();
    model.addAttribute("members", members);
    return "members/memberList"; // → View 이름!
}
````
이 결과가 내부적으로는:
```java
new ModelAndView("members/memberList", modelMap)
```
처럼 바뀌어서 `DispatcherServlet`에 전달
🧾 즉, `ModelAndView`는 HTML 파일 이름 + 데이터 객체 를 함께 들고 `DispatcherServlet`으로 돌아옴.

**📌 Step 5. ModelAndView에서 View 이름 꺼내기**
이전에 핸들러(컨트롤러)가 반환한 결과 `return "members/memberList";`
이건 실제로는 내부에서 아래처럼 ModelAndView 객체로 감싸짐:
```java
ModelAndView mav = new ModelAndView("members/memberList");
mav.addObject("members", members);
```
"members/memberList" → View 이름
members 리스트 → Model 데이터
`DispatcherServlet`은 이 `ModelAndView` 객체로부터 뷰 이름을 꺼냄.

**📌 Step 6. ViewResolver가 View 객체를 찾기**
`DispatcherServlet`: “이 뷰 이름으로 실제 화면(html 파일) 찾아줘!”

🔍 ViewResolver란?
	•	View 이름(문자열) → 실제 뷰 파일 경로(예: .html, .jsp)로 변환해줌.
    
```
ViewResolver 설정 → prefix: /templates/, suffix: .html

View 이름: "members/memberList"
→ 실제 경로: /templates/members/memberList.html
````
`ViewResolver`는 이 경로를 기반으로 View 객체를 생성해서 `DispatcherServlet`에 돌려줌.

**📌 Step 7. View 객체가 HTML 렌더링**

`DispatcherServlet`은 View 객체에게 model 데이터를 넘겨줌.
View 객체는 그 **model 데이터를 끼워 넣어 HTML을 완성**함. 

( “model을 넘긴 적이 없는데 View가 어떻게 아는 거야?”
→ 스프링이 내부에서 render(model, req, res)로 넘겨주기 때문에 View는 model 내용을 알고 있음. )

→ 하단 HTML에 members 리스트의 값이 실제로 들어감.
즉, Thymeleaf 같은 `템플릿 엔진`이 model에 담긴 데이터를 치환해서 완성된 HTML을 만들어냄.
( HTML에 있는 ${} 부분은 템플릿 엔진(Thymeleaf, JSP 등)이 서버에서 미리 치환 )

예: memberList.html
```html
<tr th:each="member : ${members}">
    <td th:text="${member.id}"></td>
    <td th:text="${member.name}"></td>
</tr>
````

**📌 Step 8. DispatcherServlet이 완성된 HTML을 사용자에게 전달**

View에서 렌더링된 완성된 HTML이 `DispatcherServlet`으로 돌아옴.

`DispatcherServlet`은 이 HTML을 HTTP 응답으로 만들어서 브라우저(클라이언트)에게 전달함.

브라우저는 이렇게 완성된 HTML을 받아서 사용자에게 보여줌.


# Spring Boot + Spring MVC 전체 실행 순서

```
✅ Spring Boot + Spring MVC 전체 실행 순서 정리

[🟢 SpringBoot 시작 구간]

1. main() 실행 → SpringApplication.run() 호출
   - 스프링 부트 앱의 진입점
   - 이 시점에 서블릿 컨테이너(내장 톰캣)도 함께 켜짐

2. ApplicationContext(스프링 컨테이너) 생성
   - Bean을 관리하는 핵심 객체 (IoC 컨테이너)

3. @ComponentScan 실행
   - 지정된 패키지에서 @Controller, @Service, @Repository, @Component 붙은 클래스 탐색

4. Bean 등록
   - 찾은 클래스들을 인스턴스(객체)로 만들어 컨테이너에 등록

5. 의존성 주입 (DI)
   - Controller → Service → Repository 순으로 자동 연결됨
   - 생성자, @Autowired 등으로 주입

6. DispatcherServlet 등록 및 초기화
   - Front Controller 역할
   - 요청 받을 준비 완료 (서블릿 맵핑: `/*`, `*.do`, 등)

--------------------------------------

[🔵 클라이언트 요청 처리 구간]

7. 사용자 브라우저에서 URL 입력 (예: /members)
   - 예: http://localhost:8080/members

8. DispatcherServlet이 요청을 받음
   - HTTP 요청을 제일 먼저 받는 중앙 관문

9. HandlerMapping 조회
   - URL과 일치하는 @RequestMapping or @GetMapping 붙은 Controller 메서드 탐색

10. HandlerAdapter 선택
   - 해당 Controller를 실행할 수 있는 어댑터 결정
   - 일반적인 경우는 RequestMappingHandlerAdapter 사용

11. Controller 실행
   - 메서드 실행: 예) `memberController.listMembers()`
   - 내부에서 Service → Repository 호출 (DB 조회 등 처리)

12. Controller에서 Model과 View 이름 반환
   - 예: `model.addAttribute("members", 리스트); return "memberList";`

13. ViewResolver 실행
   - View 이름 "memberList" → "/WEB-INF/views/memberList.jsp" 경로로 변환

14. JSP View 렌더링
   - model 데이터를 ${members} 등에 끼워 넣어 완성된 HTML 생성

15. DispatcherServlet이 완성된 HTML을 HTTP 응답으로 전송
   - 브라우저는 결과 화면을 받음
```




💡 여기서 헷갈릴 수 있는 포인트는?
	•	“Bean은 객체야? 클래스야?”
→ Bean은 스프링이 생성해서 관리하는 객체(instance) 를 말해! 클래스 그 자체는 아님.
	•	“올라간다는 게 메모리에 올라가는 건가?”
→ 좀 비유적인 표현이야. 정확히는 스프링 컨테이너 내부에 등록돼 있다는 뜻이야.

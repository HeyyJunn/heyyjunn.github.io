---
title: "[C++] 객체지향프로그래밍1 : Inheritance / Override / vptr,vtbl / downcasting (chapter 13 - 16)"
date: 2024-11-10 17:04:38 +0900
last_modified_at: 2026-09-02 03:56:42 +0900
categories:
  - "[C++] Archive"
thumbnail:
  path: "/assets/img/velog/3bbd2352-464c-4b86-be90-a7f08b232073/67c00ee507f3b923fa95c8977502f4ff2306994347b28188a021ee3c7bd71b45.jpg"
  alt: "[C++] 객체지향프로그래밍1 : Inheritance / Override / vptr,vtbl / downcasting (chapter 13 - 16)"
render_with_liquid: false
---
> 이 게시글은 대학교 객체지향프로그래밍1 (C++) 강의를 수강하며 교수님의 강의를 정리한 것입니다. **오직 개인적인 학습 기록으로 활용하기 위한 용도로 작성되었으며, 가독성이나 체계적인 정리가 부족할 수 있습니다.**

# 상속 (inheritance)
Class 는 다른 Class 로부터 속성이나 동작을 계승할 수 있다.

이를 통해 공통의 속성이나 동작을 여러 클래스가 공유하면서도 각각의 고유한 속성을 추가적으로 부여하는 것이 가능하다.

상속을 통해 다른 Class 들은 계층을 갖게 된다.

** 클래스 상속 관계 선언 **
```cpp
class Parent { };
class Child : public Parent {};
`````
Parent 의 멤버 변수/함수가 Child 클래스의 정의에 복붙 ( Parent 는 Child 에만 있는 멤버 변수/함수를 접근할 수 있다. )

![](/assets/img/velog/3bbd2352-464c-4b86-be90-a7f08b232073/956bb0e794b19321bd1bda74f34e946823a4faf0701d503cbf8d9326543d4e7c.png)

상속 관계일 때 객체의 메모리 할당
( 출처 : 객체지향프로그래밍1 문대경 교수님 강의자료 중 일부 )

## UP & DOWN CASTING
하나의 타입 (Parent) 으로 다양한 타입들 (Child 타입들) 의 "올바른 동작"을 나타낼 수 있는 것을 **"다형성"(polymorphism)** 이라고 한다.

c++ 의 가상 함수와 up-casting 은 다형성을 가능하게 한다.

### Up - casting
Child Class 의 주소/참조는 Parent class 의 주소/참조로 형변환이 가능하다.

```cpp
Child c;

Parent *ptr = &c;
Parent &ref = c;
`````
Up-casting 의 의미는 child 객체에 할당된 전체 메모리 중 Parent 부분만 사용하겠다는 뜻.

### Down - casting
**원래 Child 객체였는데 Up-casting 되어 Parent 주소/참조 로 표시된 것** 뿐이라면 다시 원상태로 Child 주소/참조로 복구하는 형변환이 가능.

```cpp
Child c;

Parent *ptr = &c;
Parent &ref = c;

Child *ptr2 = static_cast<Child *>(ptr);
Child &ref2 = static_cast<Child &>(ref);
`````

### Protected 접근 지정자

자기 자신과 파생 클래스 에서 호출할 수 있음을 나타냄

### 상속의 종류 : public, protected, private

## 상속 관계에서의 생성자/소멸자 호출
- 생성자
1. 부모 클래스의 생성자
2. 자식 객체 타입 멤버 생성자
3. 자식 생성자 몸체

- 소멸자
1. 자식 소멸자 몸체
2. 자식 객체 타입 멤버 소멸자
3. 부모 클래스의 소멸자

# 다중 상속 (Multiple Inheritance)

```cpp
class Child : public Parent1, public Parent2 {

};
`````
다중 상속도 단일 상속의 경우와 마찬가지로

1. 부모와 자식 멤버 변수 크기 총합에 맞게 객체 사이즈가 정해지고
2. 객체 사이즈 만큼 연속되는 메모리가 할당
3. 객체의 멤버 변수를 접근할 때 "객체의 시작주소 + 멤버 변수의 offset" 형태로 컴파일러가 기계어를 생성 

단, 실무적으로는 구현을 위한 상속은 단일 상속만을 사용

# 0번째 매개변수 ( temp )

# 가상 멤버 함수 (Virtual Member Function)

**실제 객체 타입에 따라 멤버 함수를 호출하기 위해서**는 클래스 정의 안에서 부모의 메소드 언언 맨 앞에 **virtual** 을 사용.

virtual 이 붙은 함수를 가상 멤버 함수라고 한다. 

가상 멤버 함수로 지정되면, 실제 호출된 함수는 **실행 시간 (run-time)** 에 결정된다. ( 추가적인 run-time 부하가 생긴다. )

## Override : 멤버 함수 재정의
virtual 로 지정된 부모의 멤버 함수를 자식 클래스가 구현 내용을 바꾸는 것.

결과적으로 virtual 은 ** "파생 클래스가 재정의한 메소드가 있다면 그걸 호출해줘" ** 라는 뜻이다.

override 할 때 **const 까지** 기재해야 한다.

```cpp
class MyClass {
public:
	virtual void f() const { }
	virtual void f() { }
};
`````

- ### 재정의(override) 제어 \#1 : override
자식 클래스 에서 "이건 **재정의**하는 것이다" 라는 **의도를 명시적으로 표시**할 때 사용한다.

- ### 재정의(override) 제어 \#2 : final
가상 함수가 더 이상 재정의되지 않아야 한다면 final 이라고 붙일 수 있다.
	
   모든 가상함수를 final 로 만들고 싶다면 클래스 정의에서 클래스 이름 뒤에 final 을 붙인다. 

 이 클래스가 자식을 갖지 못하게 하는 효과도 있다.
 ```cpp
public:
	virtual void f() override final { }
 `````

- ### 재정의(override) 제어 \#3 : 순수 가상 함수
지금까지는 부모 클래스가 가상 함수의 기본 구현을 제공했다. 

  virtual void f() {} 이는 자식이 멤버 함수를 재정의 하지 않더라도 이 기본 구현이 호출됨을 의미한다.

 위와 같이 비어있는 기본 구현을 제공할 때는 거의 자식이 재정의 하길 원하는 경우이다.
 따라서 **"재정의를 강제"** 할 수 있는 방법이 필요하다.
 
 자손 클래스가 반드시 가상 함수를 재정의 해야 된다면, 함수 선언 뒤에 = 0; 을 붙인다.
 
 순수 가상 함수를 갖는 클래스는 객체를 만들 수 없다. 이런 클래스를 **"추상 클래스"** 라고 한다.
 
 이렇게 표시된 가상함수를 "순수 가상 함수" 라고 함.
 ```cpp
 public:
 	virtual void f() = 0;
 `````

## 소멸자의 가상화
 
## 가상 함수가 구현 되는 방식  

이 상태로 시험 보러 갔습니다. 평생 비어있을거에요.

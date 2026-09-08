---
title: "[C++] 객체지향프로그래밍1 : Lambda Expression / Namespace / ADL / Nested Class (chapter 17 - 18)"
date: 2024-11-10 17:29:58 +0900
last_modified_at: 2026-09-08 08:51:49 +0900
categories:
  - "[C++] Archive"
thumbnail:
  path: "/assets/img/velog/2b9b7e47-2e14-4612-ab10-e6c81055dd8e/1a6537ad1010cab1056a99dc3a77033ffc3da9fe8a26eae0a55eb826735f1cb3.jpg"
  alt: "[C++] 객체지향프로그래밍1 : Lambda Expression / Namespace / ADL / Nested Class (chapter 17 - 18)"
render_with_liquid: false
---
> 이 게시글은 대학교 객체지향프로그래밍1 (C++) 강의를 수강하며 교수님의 강의를 정리한 것입니다. **오직 개인적인 학습 기록으로 활용하기 위한 용도로 작성되었으며, 가독성이나 체계적인 정리가 부족할 수 있습니다.**

# Lambda Expression

지금까지는 코드 안에 함수 호출을 기재했다.

다시 말해, 어떤 함수가 호출될지를 컴파일 시간에 안다고 가정한 것.

버튼을 구현하는데,

" 로딩 중이 아니라면 - 터치가 되지만
로딩 중이라면 - 기다리라는 메시지 "

를 노출하는 것과 같이 어떤 함수가 호출될지를 실행 시간에 결정하려면 어떻게 해야할까?

즉 호출할 함수를 동적으로 결정해야 할 때 ~

## Lambda

(함수 객체 중) 이름이 없는 **함수 객체**
🚨 함수가 아니라 함수 객체

![](/assets/img/velog/2b9b7e47-2e14-4612-ab10-e6c81055dd8e/37f9718a8d3d76e18a4e3b6608a42638344f62af85a381d36f2189a135706492.png)

** \[캡쳐리스트] (매개변수) ->반환타입 { 함수 몸통 } ** 와 같은 형식.

매개변수가 없다면 생략 가능

```cpp 
auto lambda = []() {
	cout << "hello lambda" << endl;
|;
`````
```cpp
lambda();
````
lambda 라는 변수에 대입만 한 것이므로 호출은 다음처럼 한다.

### \[ ] : lambda 캡쳐리스트
람다 표현식의 몸통에는

1. 전역 변수
2. 매개변수
3. 람다 안에서 정의 한 지역변수 

만 쓸 수 있다.

lambda 가 정의된 scope 에서 쓸 수 있던 **지역 변수** 도 계속 쓸 수 있으면 편리할 것이다.

이를 캡쳐리스트 라고 대괄호 안에 넘길 변수 목록을 콤마로 구분해서 기재한다.

값으로 복사할 것 : 그냥 변수 이름을 기재
참조를 넘길 것 : 변수 이름 앞에 & 을 붙인다.

![](/assets/img/velog/2b9b7e47-2e14-4612-ab10-e6c81055dd8e/21c7e6a7bd9a5d12c6a393977f8f02acb44a6e7b56cecdf6e4995506984ad5b0.png)

( 출처 : 객체지향프로그래밍1 문대경 교수님 강의자료 중 일부 )

### lambda 자체의 타입
Lambda 를 정의할 때는 auto 를 사용하면 편리
그러나, lambda 를 다른 함수에 인자로 넘길 때는, 명시적으로 lambda 타입을 기재해야 한다.

1. \#include <functional\> 을 한다.
2. lambda 타입을 std::function<반환타입(매개변수 목록)> 로 쓴다.

```cpp
#include <functional>
#include <iostream>
using namespace std;

void wrapper (const functional<void(int)> &filter, int v) {
	filter(v);
}

int main(void) {

	어쩌고 저쩌고
    
    auto filter [](int v) {
    	cout << v << endl;
	};
    
    어쩌고 저쩌고
}
`````
lambda 가 참조를 캡쳐했는데 lambda 자체를 복사해서 호출할 때는 scope 이 바뀌어 참조 대상이 사라질 수 있다.

### call by value 로 캡쳐했는데 변경하고 싶을 때

temp temp temp temp !!! 

# 함수의 기본 인자 (Default Argument)
아무 인자나 기본 값을 정할 수 있는 것이 아니다.
맨 마지막 것부터 기본 인자를 줄 수 있다.
```cpp
void f(int a, int b = 10(;
``````

# 이름 공간 (Namespace)

symbol(=이름)
compiler 가 기계어 파일인 오브젝트 파일 생성

linker 는 오브젝트 파일들을 모아서 심볼

심볼, 즉 이름은 오직 한번만 사용할 수 있다. 

중복되는 symbol 을 피하는데 한계
특히 외부에서 가져온 라이브러리를 쓸 때, 라이브러리 개발자가 사용한 이름은 우리가 어쩔 수 없다.

의도적으로 cpp 구현을 여러 개의 버전으로 관리하고 싶을 수 있다.

심볼들을 논리적인 단위로 묶어 구분, 이를 "이름 공간" 이라고 함.

## namespace 의 특징
1. 같은 namespace 안에 정의된 심볼은 같은 scope 안에 있음. 별다른 표기 없이 사용 가능.
2. namespace 밖에서는 그 안의 심볼들이 보이지 않는다. (접근 불가, 범위지정 연산자 :: 를 사용해야 한다)
3. namespace 안에 중첩되는 또 다른 namespace 정의 가능

## namespace 정의
class 와 달리 뒤에 ; 가 안붙음

```cpp
namespace MyNamespace {
	int var;
    void f();
    
    class MyClass {
    public:
    	int a;
	};
}
`````

namespace 는 한번 정의하면 거기서 끝난게 아니라
열려 있는 상태로 계속해서 심볼을 추가할 수 있음.

## namespace 안에 변수/함수/멤버 함수 정의하기
1. header 파일에는 변수/함수의 선언과 클래스 정의
2. cpp 파일에는 변수/함수/멤버함수의 정의를 둔다.

cf) myfile.h
```cpp
namespace N {
	extern int var;
    void f();
    
    class A {
    public:
    	void g();
    };
}
`````
- ### (추천) 방법\#1 - namespace 를 다시 열어 정의 추가하기
```cpp
#include <iostream>
#include "myfile.h"
using namespace std;

namespace N {
	int var;
    void f() { cout << "f\n"; }
	void A::g() { cout << "A::g\n"; }
`````
- ### 방법\#2 - 범위 지정자를 써서 명시적으로 한정하기

```cpp
int N::var;
`````

## 범위지정자를 이용해 네임스페이스 내부 심볼 이용하기
```cpp
#include "myfile.h"

int main (void) {
	N::A obj;
    obj.g();
}
`````
범위 지정 연산자 :: 를 namespace 없이 쓰면 전역 영역을 가르킴.

# using 선언
매번 범위 지정 연산자로 한정하는 것은 귀찮다.
앞으로 언급되는 이 특정 심볼은 namespace 안의 특정 심볼임을 명시.
```cpp
using std::cout;

int main(void) {
	cout << "hello" << endl;
}
`````
using 은 scope 의 적용을 받는다.

## using 지시자 (Using - directive)
전체 namespace 를 using 으로 지정할 수도 있음. " using 지시자 " 라고 한다.

```cpp
using namespace std;
`````

**🚨 using 을 남발하는 것은 좋은 습관이 아님.
전역 영역에 넣는 것은 권장하지 않음. **

header file 에도 마찬가지. ( 해당 파일을 include 하는 모든 파일에 영향을 줌 )


### using 의 활용 예시 ( 구현의 버전 스위칭 )
```cpp
namespace version1 {
	void f();
}
namespace version2 {
	void f();
}

int main (void) {
	
    구현의 버전을 아래 using 으로 통제
    using namespace version1;
    
    위의 using 에 따라 선택된다.
    f();
}
`````

```cpp

`````
## namespace 별명(Alias)을 이용한 축약
namespace 가 길 때 범위 지정 연산자를 매번 쓰는 것은 귀찮을 수 있다.

namespace 에 다른 이름을 붙여서 사용 가능.
```cpp
namespace S = std;

int main (void) {
	S::cout << "hello";
}
`````
구현의 버전을 스위칭 하는 용도로 활용가능.
```cpp
namespace version1 {
	void f();
}
namespace version2 {
	void f();
}

int main (void) {
	namespace current = version1;
    currrent::f();
}
`````
## Unnamed Namespace (익명 namespace)
namespace 에 이름을 주지 않으면 익명 namespace
해당 namespace 는 한 파일 안에서만 동작한다.

## Nested Namespace (중첩 namespace)
namespace 안에서 새로운 namespace 를 선언할 수 있다.
```cpp
namespace N {
	void f();
    
    namespace internal {
    	int var;
    }
}

int main (void) {
	N::f();
    N::internal::var = 10;
}
`````
## Namespace 조합 (Namespace Composition)

서로 다른 namespace 에 흩어져 있는 심볼을 뽑아서 새 namespace 를 만들 수 있다. 

양쪽 모두 Student 라는 클래스가 있어서 이름 충돌이 발생하는 경우, using computer::Student; 로 특정 namespace 의 클래스를 사용가능.
```cpp
namespace engineering {
	using namespace computer;
    using namespace electrical;
    
    using computer::Student;
}
`````
## class = 일종의 namespace

# Argument Dependent Lookup (ADL)
함수 이름을 찾을 때 실행 인자의 타입이 사용자 정의 타입 (클래스) 이면 이 타입이 정의된 **이름공간"도"** 같이 찾는 것.

![](/assets/img/velog/2b9b7e47-2e14-4612-ab10-e6c81055dd8e/2b34ed3d5edbddd6c1741957e0087596408cd7d01912b5e224c1362ecad70c6f.png)

## ADL 보다는 멤버 함수가 우선 됨 
![](/assets/img/velog/2b9b7e47-2e14-4612-ab10-e6c81055dd8e/2d1ec78984d26101ec29a34cd7b35cdcdd0ad8298f7397a3f39a392bbe1a663c.png)


# C++ 중첩 클래스 (Nested Class)

class 정의 안에 다른 class 정의
안쪽에 정의된 클래스를 nested class 라고 한다.

Nested Class 에 대한 접근은 접근 지정자를 따른다.

해당 클래스에 한정되는 클래스를 목적에 따라 추가가능
- internal 목적이면 protected 나 private
- 외부에서 사용하게 하는 목적이라면 public

```cpp
class A {
public:
	class Nested {
    public:
    	void f();
	private:
    	int a;
	};
    void f();
    
    private:
    	int a;
};

void A::f() {}

void A::Neested::f() {}

int main (void) {
	A a;
    a.f();
    
    A::Nested nested;
    nested.f();
}
`````
## C++ 클래스 안에 enum 정의하기
enum 은 종류를 열거할 때 이용된다. (enumerate)

```cpp
class A {
public:
	enum Color {
    	Red,
        Green,
        Blue,
	};
};

int main(void) {
	A::Color c1 = A::Blue; // ok
    A::Color c2 = A::Color::Red; // ok either.
`````

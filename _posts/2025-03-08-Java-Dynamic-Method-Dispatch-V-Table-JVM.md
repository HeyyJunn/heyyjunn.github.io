---
title: "[Java] Dynamic Method Dispatch & V-Table (JVM)"
date: 2025-03-08 22:36:16 +0900
last_modified_at: 2026-09-07 09:36:51 +0900
categories:
  - "[Java] Archive"
render_with_liquid: false
---
>💡 이 게시글은 김영한 강사님의 자바 강의를 수강하며 학습한 내용을 중요한 키워드 중심으로 정리한 개인 학습 기록입니다. **오직 기억 복기를 위한 목적으로 작성되었으며, 모든 내용을 포함하지 않으므로 체계적인 학습 자료로는 적합하지 않습니다.** 

" Java는 C++처럼 virtual을 명시하지 않아도, (대부분의) 인스턴스 메서드 호출이 기본적으로 ‘런타임에 실제 객체 타입’을 기준으로 결정된다(동적 디스패치). "

### C++을 배우고 Java를 학습하며 느낀 혼란
C++ 을 배우고 Java 를 학습하니 JVM 자바 가상 머신이란 개념과 가상함수 테이블 V-Table 이란 개념이 낯설었다.

C++ 은 기본적으로 Static-Binding(정적 바인딩) 에 virtual 키워드를 사용해야 가상 함수가 생성되어 Dynamic-Binding 이 가능했다면, Java 는 메서드 영역에 자동으로 V-Table 이 생성되어 (Compile-Time), Run-Time에 Dynamic-Dispatch 가 작동한다는 점에서 혼란이 있었다. 

특히 오랜만에 다형성 ( override, up/down casting ) 개념을 접하는데, 강좌엔 내부적으로 어떻게 동작하는지 설명이 없어 JVM 과 V-table 내부 작동 방식을 공부해보기로 했다.


> 💡 본 필기 내부에 강좌에서 제공된 자료 이미지와 외부자료 캡쳐 이미지가 있어 일시적으로 블러처리 합니다.

![](/assets/img/velog/7bd24f35-d6e6-471c-becc-2dbb512acc4d/2205edc1b937b27313be3176a7f59ba268c8cd075136ca96c57a90443ae742dd.jpg)

![](/assets/img/velog/7bd24f35-d6e6-471c-becc-2dbb512acc4d/b864ad09c31bb7d7d25cb0fef43ae37c0d1cf1ce7fbaa2d5ab0a7e14ce19ba26.jpg)

### 1. 모든 instance method는 기본적으로 V-table 을 통해 동적바인딩 된다.

가상 함수(Virtual-Function)는 객체의 "실제 타입" 을 기준으로 메서드를 호출하는 기능을 의미한다.

즉, 업캐스팅 되어도, 실제 객체가 자식 타입이면 자식 클래스의 메서드가 실행될 수 있다는 의미이다. 

### 2. Compile-Time 에 V-Table 이 생성되고, Run-Time 에 Method 호출이 V-Table 을 통해 결정된다 (Dynamic Binding)

각 클래스가 로드될 때, 메서드 영역(Method Area)에 클래스 정보와 함께 V-Table이 생성된다. (Compile-Time)

부모 클래스의 V-Table을 상속받고, 자식이 오버라이딩하면 V-Table을 덮어써 갱신 되는 것이다.

이후 Run-Time 에 Heap 영역의 객체가 참조하는 V-Table 포인터를 따라가면서 실행할 메서드를 결정하게 된다.

### ∴ 그러므로,

해당 2가지를 알지 못하여 다형성1 section 의 override 를 학습하며 계속해서 의구심이 들었던 것이다.

JVM 이 클래스 로더를 통하여 클래스 정보를 Method Area 에  로드하고 V-Table을 생성하여 지닌다는 점을 모르니, **가상 함수를 명시적으로 만들지도 않았는데 어떻게 JVM에서 오버라이딩된 메서드를 자동으로 동적 바인딩하는지 의문이 들었던 것이다.😇** ( C++ 은 virtual keyword 를 명시적으로 사용해야 가상함수가 생성되기 때문 )

앞으로 학습을 해나갈 때 Compile-Time, Run-Time 개념을 구분하여 사고하는 것이 이해에 도움이 될 것 같다.

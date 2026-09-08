---
title: "[Java] Polymorphism"
date: 2025-03-14 20:31:33 +0900
last_modified_at: 2026-09-02 03:56:04 +0900
categories:
  - "[Java] Archive"
thumbnail:
  path: "/assets/img/velog/37a2bbb0-0fe1-4a3b-8de3-405a08a9e1b7/00bc1e9539f68d2e5bd93c7911d6e950200c3afafea695a1beda4401843833b9.jpg"
  alt: "[Java] Polymorphism"
render_with_liquid: false
---
>💡 이 게시글은 김영한 강사님의 자바 강의를 수강하며 학습한 내용을 중요한 키워드 중심으로 정리한 개인 학습 기록입니다. **오직 기억 복기를 위한 목적으로 작성되었으며, 모든 내용을 포함하지 않으므로 체계적인 학습 자료로는 적합하지 않습니다.** 

>임시 저장본이 날아가는 경우가 있어 demo로 업로드

## Section12 (다형성2) 

### 추상클래스

동물(`Animal` )과 같이 부모 클래스는 제공하지만, 실제 생성되면 안되는 클래스를 추상 클래스라 한다.

추상클래스는 추상적인 개념을 제공하는 클래스.
따라서 인스턴스가 존재하지 않으며 상속을 목적으로 상용되고, 부모 클래스 역할을 담당한다.

추상 클래스는 클래스를 선언할 때 앞에 추상이라는 의미의 `abstract` 키워드를 붙여주면 된다.


```java
abstract class AbstractAnimal {...}
```

### 추상메서드
부모 클래스를 상속 받는 자식 클래스가 반드시 오버라이딩 해야 하는 메서드를 부모 클래스에 정의할 수 있다. 

추상 메서드는 이름 그대로 추상적인 개념을 제공하는 메서드이다. 따라서 실체가 존재하지 않고,
메서드 바디가 없다.

```java
public abstract void sound();
```

**🌱 추상 메서드가 하나라도 있는 클래스는 추상 클래스로 선언해야 한다.**

**🌱 추상 메서드는 상속 받는 자식 클래스가 반드시 오버라이딩 해서 사용해야 한다.**

### (순수 추상 클래스)
```java
public abstract class AbstractAnimal {
	public abstract void sound();
	public abstract void move();
}
````
**상속하는 클래스는 모든 메서드를 구현해야 한다.**
자바는 순수 추상 클래스를 더 편리하게 사용할
수 있도록 `인터페이스`라는 개념을 제공한다.

### 인터페이스
인터페이스는 다중 구현(다중 상속)을 지원한다.
메서드에 `public abstract` 를 생략할 수 있다. 참고로 생략이 권장된다.

인터페이스에서 멤버 변수는 `public` , `static` , `final` 이 모두 포함되었다고 간주된다. `final` 은 변수의 값을 한
번 설정하면 수정할 수 없다는 뜻이다
```java
public interface InterfaceAnimal {
	public abstract void sound();
	public abstract void move();
}
```
`제약` 인터페이스를 만드는 이유는 인터페이스를 구현하는 곳에서 인터페이스의 메서드를 반드시 구현해라는 규약(제약)을 주는 것.
`다중구현` 인터페이스는 부모를 여러명 두는 다중
구현(다중 상속)이 가능하다.


### 인터페이스 다중구현
```java
package diamond;

public class Child implements InterfaceA, InterfaceB {
    @Override
    public void methodA() {}

    @Override
    public void methodB() {}

    @Override
    public void methodCommon() {}
}
```

```java
public class Bird extends AbstractAnimal implements Fly, Swim {
```
`extends` 를 통한 상속은 하나만 할 수 있고 `implements` 를 통한 인터페이스는 다중 구현 할 수 있기 때문에 둘이 함
께 나온 경우 `extends` 가 먼저 나와야 한다.

### OCP (Open-Closed Principle)
`Open for extension` 새로운 기능의 추가나 변경 사항이 생겼을 때, 기존 코드는 확장할 수 있어야 한다.
`Closed for modification` 기존의 코드는 수정되지 않아야 한다.

기존의 코드 수정없이 새로운 기능을 추가할 수 있어야 한다.
확장에는 열려있고, 변경에는 닫혀 있다는 의미. 
즉, 핵심 클라이언트의 코드를 변경하지 않도록 하는 것.

`main()` 은 전체 프로그램을 설정하고 조율하는 역할을 한다. 이런 부분은 OCP를 지켜도 변경이 필요하다.

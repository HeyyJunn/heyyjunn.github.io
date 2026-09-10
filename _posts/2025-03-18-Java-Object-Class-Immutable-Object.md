---
title: "[Java] Object Class, Immutable Object"
date: 2025-03-18 18:56:00 +0900
last_modified_at: 2026-09-02 03:56:11 +0900
categories:
  - "Java"
thumbnail:
  path: "/assets/img/velog/cf211993-d985-4368-9091-dd1cb1b952a2/f340b9b2ab3bfdbda7e069de204203c35a60fa3f785f3e7fe00d8e0e2aae3331.jpg"
  alt: "[Java] Object Class, Immutable Object"
render_with_liquid: false
---
>💡 이 게시글은 김영한 강사님의 자바 강의를 수강하며 학습한 내용을 중요한 키워드 중심으로 정리한 개인 학습 기록입니다. **오직 기억 복기를 위한 목적으로 작성되었으며, 모든 내용을 포함하지 않으므로 학습 자료로는 적합하지 않습니다.** 

>임시 저장본이 날아가는 경우가 있어 demo로 업로드

## Section2 (Object Class)

**Object Class**

자바에서 모든 클래스의 최상위 부모 클래스는 항상 `Object` 클래스이다.

클래스에 상속 받을 부모 클래스를 명시적으로 지정하면 `Object` 를 상속 받지 않는다.

```java
package lang.object;

public class ObjectMain {
    public static void main(String[] args) {
        Child child = new Child();
        child.childMethod();
        child.parentMethod();
        
        // toString()은 Object 클래스의 메서드
        String string = child.toString();
        System.out.println(string);
    }
}
```
1. `child.toString()` 을 호출한다.
2. 먼저 본인의 타입인 `Child` 에서 `toString()` 을 찾는다. 없으므로 부모 타입으로 올라가서 찾는다.
3. 부모 타입인 `Parent` 에서 찾는다. 없으므로 부모 타입으로 올라가서 찾는다.
4. 부모 타입인 `Object` 에서 찾는다. `Object` 에 `toString()` 이 있으므로 이 메서드를 호출한다.

자바에서 모든 객체의 최종 부모는 `Object` 다

모든 클래스가 `Object` 클래스를 상속 받는 이유는 다음과 같다.
- 공통 기능 제공
- 다형성의 기본 구현

```java
package lang.object.poly;

public class ObjectPolyExample1 {
    public static void main(String[] args) {
        Dog dog = new Dog();
        Car car = new Car();

        action(dog);
        action(car);
    }

    private static void action(Object obj) {
        // obj.sound(); // 컴파일 오류, Object는 sound()가 없다.
        // obj.move(); // 컴파일 오류, Object는 move()가 없다.

        // 객체에 맞는 다운캐스팅 필요
        if (obj instanceof Dog dog) {
            dog.sound();
        } else if (obj instanceof Car car) {
            car.move();
        }
    }
}
````

**Object 배열**
```java
package lang.object.poly;

public class ObjectPolyExample2 {
    public static void main(String[] args) {
        Dog dog = new Dog();
        Car car = new Car();
        Object object = new Object(); // Object 인스턴스도 만들 수 있다.

        Object[] objects = {dog, car, object}; // 다양한 객체를 Object 배열에 저장
        size(objects);
    }

    private static void size(Object[] objects) {
        System.out.println("전달된 객체의 수는: " + objects.length);
    }
}
```

**toString()**
`Object.toString()` 메서드는 객체의 정보를 문자열 형태로 제공한다. 

`Object` 가 제공하는 `toString()` 메서드는 기본적으로 패키지를 포함한 객체의 이름과 객체의 참조값(해시
코드)를 16진수로 제공한다.

```java
package lang.object.tostring;

public class ToStringMain1 {
    public static void main(String[] args) {
        Object object = new Object();
        String string = object.toString();

        // toString() 반환값 출력
        System.out.println(string);

        // object 직접 출력
        System.out.println(object);
    }
}
```

```java
java.lang.Object@a09ee92
java.lang.Object@a09ee92
````

```java
public static String valueOf(Object obj) {
return (obj == null) ? "null" : obj.toString();
}
````

`System.out.println()` 메서드는 사실 내부에서 `toString()` 을 호출한다.

`Object` 타입(자식 포함)이 `println()` 에 인수로 전달되면 내부에서 `obj.toString()` 메서드를 호출해서 결과
를 출력한다.

**toString() 오버라이딩**

`Object.toString()` 메서드가 클래스 정보와 참조값을 제공하지만 이 정보만으로는 객체의 상태를 적절히 나타내지 못한다. 그래서 보통 `toString()` 을 재정의(오버라이딩)해서 보다 유용한 정보를 제공하는 것이 일반적이다.

```java
@Override
public String toString() {
    return "Dog{" +
            "dogName='" + dogName + '\'' +
            ", age=" + age +
            '}';
}
```


```java
package lang.object.tostring;

public class ToStringMain2 {
    public static void main(String[] args) {
        Car car = new Car("Car1");
        Dog dog1 = new Dog("Dog1", 5);
        Dog dog2 = new Dog("Dog2", 10);

        System.out.println(car.toString());
        System.out.println(dog1.toString());
        System.out.println(dog2.toString());

        System.out.println(car);
        System.out.println(dog1);
        System.out.println(dog2);

        ObjectPrinter.print(car);
        ObjectPrinter.print(dog1);
        ObjectPrinter.print(dog2);

        String refValue1 = Integer.toHexString(System.identityHashCode(dog1));
        System.out.println(refValue1);
        String refValue2 = Integer.toHexString(System.identityHashCode(dog2));
        System.out.println(refValue2);
    }
}

```
```
lang.object.tostring.Car@5f184fc6
Dog{dogName='Dog1', age=5}
Dog{dogName='Dog2', age=10}
lang.object.tostring.Car@5f184fc6
Dog{dogName='Dog1', age=5}
Dog{dogName='Dog2', age=10}
객체 정보 출력: lang.object.tostring.Car@5f184fc6
객체 정보 출력: Dog{dogName='Dog1', age=5}
객체 정보 출력: Dog{dogName='Dog2', age=10}
506e1b77
4fca772d
```

**Object와 OCP**

**구체적인 것에 의존** <<< **추상적인 것에 의존👍**
```java
public class ObjectPrinter {
    public static void print(Object obj) {
        String string = "객체 정보 출력: " + obj.toString();
        System.out.println(string);
    }
}
```

**equals() - 동일성과 동등성**

**동일성(Identity)**: `==`연산자를 사용해서 두 객체의 참조가 동일한 객체를 가리키고 있는지 확인
**동등성(Equality)**: `equals()` 메서드를 사용하여 두 객체가 논리적으로 동등한지 확인

```java
    @Override
    public boolean equals(Object o) {
        if (this == o) return true;
        if (o == null || getClass() != o.getClass()) return false;
        UserV2 userV2 = (UserV2) o;
        return Objects.equals(id, userV2.id);
    }
}
```
```java
package lang.object.equals;

public class EqualsMainV2 {
    public static void main(String[] args) {
        UserV2 user1 = new UserV2("id-100");
        UserV2 user2 = new UserV2("id-100");

        System.out.println("identity " + (user1 == user2));
        System.out.println("equality " + user1.equals(user2));
    }
}

//identity false
//equality true
```

## Section3 (Immutable Object)

`Side Effect`참조값을 다른 변수에 대입하는 순간 여러 변수가 하나의 객체를 공유하게 된다. 쉽게 이야기해서 **객체의 공유를 막을수 있는 방법이 없다.**

**불변이라는 단순한 제약을 사용해서 사이드 이펙트라는 큰 문제를 막을 수 있다.**
	
객체의 공유 참조는 막을 수 없다. 그래서 객체의 값을 변경하면 다른 곳에서 참조하는 변수의 값도 함께 변경되는 사이드 이펙트가 발생한다. 

사이드 이펙트가 발생하면 안되는 상황이라면 불변 객체를 만들어서 사용하면 된다.

불변 객체는 값을 변경할 수 없기 때문에 사이드 이펙트가 원천 차단된다.

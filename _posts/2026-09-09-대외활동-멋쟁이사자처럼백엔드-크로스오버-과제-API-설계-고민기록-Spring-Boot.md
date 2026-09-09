---
title: "[대외활동] 멋쟁이사자처럼·백엔드 크로스오버 과제 API 설계 고민기록 (Spring Boot)"
date: 2026-09-09 18:22:33 +0900
last_modified_at: 2026-09-09 18:39:48 +0900
thumbnail:
  path: "/assets/img/velog/7d4c85ee-4617-427a-8666-f6e98067001e/26b945ea969aa3c007428930527141e5c6ea0ca00935feb3b89ba1fa9338d044.png"
  alt: "[대외활동] 멋쟁이사자처럼·백엔드 크로스오버 과제 API 설계 고민기록 (Spring Boot)"
render_with_liquid: false
---
> 멋쟁이사자처럼(대학) 11주차 크로스오버 과제

> 간단한 과제였지만 구조와 흐름, 코드 설계를 어떻게 리팩토링 해야할 것인가에 집중했다.

프론트와 협업해볼 프로젝트- 감정일기
https://emotion-diary.winterlood.com/

## 백엔드 API 구현 고려사항

- 월별 일기 목록 조회
- 단일 일기 상세 조회
- 일기 생성
- 일기 수정
- 일기 삭제

![](/assets/img/velog/7d4c85ee-4617-427a-8666-f6e98067001e/8d5cdf66c9e5b41ea870b8eb4d97eadceb235577ecc548f677a7e9645afb3e36.png)

## ☑️ 고민1.  toEntity() / toDto() 위치와 필요성

**✅ “toEntity(), toDto() 내부에 localDateTime → timestamp(ms) 변환 로직 넣을 것인가?” ↔️ "Service 내부에 구현할 것인가?"**

프론트는 `timestamp(epoch time)` 의 표현방식으로 api를 요청하는 것이 가볍지만, 백엔드 쪽에서는 엔지니어가 보기 편하고 날짜를 계산하기 좋은 `LocalDateTime` 을 사용하게 된다.

해당 변환 로직을 `Service` 에 구현할 것인지, `Dto` 의 매핑 메서드 (toEntity()) 에 구현할 것인지에 대한 고민이었다.

우선 toEntity() 내부에 변환 로직을 넣기도 한 이유는

1. 책임을 한 곳에 묶어서 처리하고자 함.
2. Service 내부 코드를 깔끔하게 작성하기 위함

변환 로직이 필요한 곳마다 구현하는 것보다 DTO 의 toEntity 내부에 구현함으로서 DB 에 넣을 수 있는 Entity 객체를 만들고자 하였다.

```java
Diary diary = diaryRequest.toEntity();
diaryRepository.save(diary);
```

## ☑️ 고민2. Entity → DiaryResponse 변환 방식
** ✅ Entity → DTO 변환을 어떻게 할까? **

**① 생성자 직접 호출 방식**
``` java
return new DiaryResponse(
    diary.getId(),
    convertToMillis(diary.getCreatedDate()),
    diary.getEmotionId(),
    diary.getContent()
);
```
생성자를 직접 호출하는 방식은 간단하고 한눈에 볼 수 있다는 장점이 있었지만, **비즈니스 로직**을 구현하는 `Service` 에서 응답 DTO 을 변환하는 것까지 구현한다는게 불필요 하다고 생각하였다.

DiaryResponse 에 새로운 필드를 추가할 시, 전부 수저앻야 한다는 점이 큰 단점으로 작용하였다.

**② Entity 안에 toDto() 넣기**
```java
public DiaryResponse toDto() {
    return new DiaryResponse(
        id,
        createdDate.atZone(ZoneId.of("Asia/Seoul")).toInstant().toEpochMilli(),
        content
    );
}
```

`diary.toDto()` 로 호출하는 것이 가장 편리해보였고, toDto 란 메서드명 역시 그 의미가 직접적으로 와닿았다.

하지만 Entity 클래스는 데이터베이스 테이블과 직접적으로 매핑되는 클래스로서 주된 목적이 **DB 와 데이터를 주고 받는 것**이므로, 

클라이언트와 응답용으로 설계된 DTO 를 알고 있는다는 것이 **책임분리 원칙에 어긋**난다고 생각하였다고, **계층 간 불필요한 의존성을 초**래할 것이라 생각하였다.


**③ ResponseDTO 내부에 fromEntity() 만들기**
```java
// DiaryResponse.java
public static DiaryResponse fromEntity(Diary diary) {
    return new DiaryResponse(
        diary.getId(),
        convertToMillis(diary.getCreatedDate()),
        diary.getEmotionId(),
        diary.getContent()
    );
}
```

```java
    private static Long convertToMillis(LocalDateTime dataTime) {
        Instant instant = dataTime.atZone(ZoneId.of("Asia/Seoul")).toInstant();
        return instant.toEpochMilli();
    }
```    
DTO 가 응답 구조를 책임진다는 것이 관심사가 가장 명확해보였고, Service 는 단순히 `fromEntity()` 만 호출하면 되므로 가장 효율적인 구조라 생각하였다. 


## ☑️ 고민3. Entity 업데이트 방식
✅ **Service에서 Entity의 필드를 수정해야 할 때 어떤 방식으로 할까?**

**① Setter 직접 사용**
```java
diary.setContent(dto.getContent());
diary.setEmotionId(dto.getEmotionId());
````
가장 직관적이고 간단하지만, 유지보수 시 수정해야 할 곳이 여러 군데 생기기 쉬울 것이라 생각하였다.

**② Entity 내부에 updateFrom(DTO) 메서드 작성**
```java
diary.setContent(dto.getContent());
diary.setEmotionId(dto.getEmotionId());
diary.setCreatedDate(dto.toLocalDateTime());
````
해당 고민 역시 Entity가 DTO를 알게 된다는 게 가장 큰 단점으로 작용하였고, 계층 분리를 위반하므로 적절치 못한 생각이였다.

**③ Request DTO 내부에 updateEntity(Entity) 메서드 작성**
```java
public void updateEntity(Diary diary) {
    diary.setContent(this.content);
    diary.setEmotionId(this.emotionId);
    diary.setCreatedDate(this.toLocalDateTime());
}
```	
```java
// DiaryService.java
    public DiaryResponse updateDiary(Long id, DiaryRequest diaryRequest) {
        Optional<Diary> optional = diaryRepository.findById(id);
        if (optional.isPresent()) {
            Diary diary = optional.get();
            diaryRequest.updateEntity(diary);
            diaryRepository.save(diary);
            return DiaryResponse.fromEntity(diary);
        }
        return new DiaryResponse(); // 예외처리 (없음)
    }
```

Entity는 DB 구조를 책임지는 모델 객체로만 사용하고 싶은 목적이 있었고, **수정 로직은 한 군데에 몰아둘 수 있어서 응집도가 높으며 재사용도 쉽다**는 장점이 있었다.

## ☑️ 고민4. 계층에 따른 메서드 네이밍

![](/assets/img/velog/7d4c85ee-4617-427a-8666-f6e98067001e/0cc6d61cd2b68e2f4d4f916b2831c79b51d111657d94eaca73b5c860b40f5b35.png)

Service 계층에서 findBy~ 네이밍을 주로 사용했는데,
이는 사실 Repository에 적합한 네이밍이기 때문에
Service에서는 get~이나 목적 중심의 네이밍으로 구분할 필요를 느꼈다.
그래서 각 계층의 역할에 맞게 메서드 네이밍을 정리하고 통일하고자 한다.

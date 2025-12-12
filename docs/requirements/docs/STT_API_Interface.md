## 코드

* server : api 서버 관련 코드들
* speechpro : 발음 평가 관련 코드들 + kaldi
* third_party : libraries

## third party library

자동 빌드 하지 않고 third_party directory에서 빌드한 것으로 사용하였습니다.
CMakeLists.txt 의 내용 참고

* a259_neural_voice_activity_detection (http://112.220.79.222:20200/leehyun22/a259_neural_voice_activity_detection)
* curl-8.12.1
* FFmpeg (gpl 제거 )
* gtp_solution_bf (http://112.220.79.222:20200/jangkyu/gtp_solution_bf)
* onnxruntime-linux-x64-1.15.1

## 테스트 서버
stt api서버 ws://112.220.79.218:33085/ws
stt 유창성 ws://112.220.79.218:33043/ws

## API 설명

생각하고 있는 시나리오의 흐름에 따라 API 를 순서대로 나열하였습니다.

1. 문장의 Noramlize 작업 수행 (구 pronmmaper의 GetNormalizeText)

    - Request

        | HTTP endpoint | conent-type | method |
        |---|:---:|:---:|
        | /speechpro/normalize | application/json | POST |

        ```sh
        curl -X POST -H "Content-Type: application/json" http://<주소>:<포트>/speechpro/normalize -d '
        {
            "id": "1000",
            "text": "i need 100$"
        }'
        ```

    - Response

        | HTTP error code | description |
        |---|:---:|
        | 200 | OK |
        | 400 | Bad Request |
        | 500 | Internal Server Error |

        body
        ```js
        {
        "id": "1000",
        "error_code": 0,
        "text": "i need 100$",
        "result": "I need one hundred dollar"
        }
        ```

2. IPA 발음열로 부터 ARPA 발음열 생성 (구 pronmmaper의 GetArpaByIpaSentence)

    ipa 발음열로 부터 arpa 발음열을 얻는 기능을 수행합니다.

    - Request

        | HTTP endpoint | conent-type | method |
        |---|:---:|:---:|
        | /speechpro/arpa | application/json | POST |

        ```sh
        curl -X POST -H "Content-Type: application/json" http://<주소>:<포트>/speechpro/arpa -d '
        {
            "id": "1000",
            "text": "d ʌ_b ʌ l_j u"
        }'
        ```

    - Response

        | HTTP error code | description |
        |---|:---:|
        | 200 | OK |
        | 400 | Bad Request |
        | 500 | Internal Server Error |

        body
        ```js
        {
            "error_code":0,     // error code : 정상시 0
            "id":"1000",        // 전달된 id 값
            "text": "d ʌ_b ʌ l_j u",    // 전달된 ipa 발음열
            "result": "D AH_B AH L_Y UW"    // 변환된 arpa 발음열
        }
        ```

3. 문장으로 부터 단어목록 얻기 (구 pronmmaper의 ParseSentence)

    - Request

        | HTTP endpoint | conent-type | method |
        |---|:---:|:---:|
        | /speechpro/sentence | application/json | POST |

        ```sh
        curl -X POST -H "Content-Type: application/json" http://<주소>:<포트>/speechpro/sentence -d '
        {
            "id": "1000",
            "text": "i need 100$"
        }'
        ```

    - Response

        | HTTP error code | description |
        |---|:---:|
        | 200 | OK |
        | 400 | Bad Request |
        | 500 | Internal Server Error |

        body
        ```js
        {
            "id": "1000",
            "error_code": 0,
            "text": "i need 100$",
            "result": [
                5,
                [
                    "I",
                    "NEED",
                    "ONE",
                    "HUNDRED",
                    "DOLLAR"
                ]
            ]
        }
        ```

4. 발음평가 할 문장에 대한 발음 생성 (구 pronmmaper의 CreateTranscription)

    문장으로 부터 발음열을 얻는 기능을 수행합니다.

    - Request

        | HTTP endpoint | conent-type | method |
        |---|:---:|:---:|
        | /speechpro/gtp | application/json | POST |

        ```sh
        curl -X POST -H "Content-Type: application/json" http://<주소>:<포트>/speechpro/gtp -d '
        {
            "id": "1000",
            "text": "안녕하세요"
        }'
        ```

    - Response

        | HTTP error code | description |
        |---|:---:|
        | 200 | OK |
        | 400 | Bad Request |
        | 500 | Internal Server Error |

        body
        ```js
        {
            "error_code":0,     // error code : 정상시 0
            "id":"1000",        // 전달된 id 값
            "text":"안녕하세요",    // 전달된 문장
            "syll_ltrs":"안_녕_하_세_요",   // 글자단위 구분자인 '_'을 확인할 수 있습니다.
            "syll_phns":"aa nf_nn yv ng_h0 aa_s0 ee_yo" // 글자단위 발음열 생성
        }
        ```

        body (여러단어로 구성된 문장의 경우 예제)
        ```js
        {
            "error_code":0,
            "id":"1000",
            "text":"만나서 반갑습니다.",
            "syll_ltrs":"만_나_서|반_갑_씀_니_다",  // 단어 구분자인 '|'을 확인할 수 있습니다.
            "syll_phns":"mm aa nf_nn aa_s0 vv|p0 aa nf_k0 aa pf_ss xx mf_nn ii_t0 aa"
        }
        ```

        body (error 발생의 경우)
        ```js
        {
            "id": "1000",
            "error_code": error code,
            "result": "error message"
        }
        ```

5. 발음평가 할 문장에 대한 모델 생성

    /speechpro/gtp 에서 생성된 결과를 입력으로 넣어 모델을 생성하는 기능을 수행합니다.

    - Request

        | HTTP endpoint | conent-type | method |
        |---|:---:|:---:|
        | /speechpro/model | application/json | POST |

        ```sh
        curl -X POST -H "Content-Type: application/json" http://<주소>:<포트>/speechpro/model -d '
        {
            "id": "1000",
            "text": "안녕하세요",
            "syll_ltrs": "안_녕_하_세_요",
            "syll_phns": "aa nf_nn yv ng_h0 aa_s0 ee_yo"
        }'
        ```

    - Response

        | HTTP error code | description |
        |---|:---:|
        | 200 | OK |
        | 400 | Bad Request |
        | 500 | Internal Server Error |

        body
        ```js
        {
            "error_code":0,     // error code : 정상시 0
            "id":"1000",        // 전달된 id 값
            "fst":"1v2yfgYAAAB2ZWN0b3IIAAAAc3RhbmRhcmQCAAAA ....",    // 생성된 모델
        }
        ```

        body (error 발생의 경우)
        ```js
        {
            "id": "1000",
            "error_code": error code,
            "result": "error message"
        }
        ```

6. wave upload를 통한 발음평가

    /speechpro/gtp<br/>
    /speechpro/model<br/>
    순서대로 수행한 결과를 입력으로 넣어 발음평가 결과를 얻어냅니다.<br/>

    - Request

        | HTTP endpoint | conent-type | method |
        |---|:---:|:---:|
        | /speechpro/scorefile | multipart/form-data | POST |

        body
        ```sh
        curl -X "POST" \
        "http://<주소>:<포트>/speechpro/scorefile" \
        -H "accept: application/json" \
        -H "Content-Type: multipart/form-data" \
        -F "wav_usr=@an.wav" \
        -F 'config={
            "id": "1000",
            "text": "안녕하세요",
            "syll_ltrs": "안_녕_하_세_요",
            "syll_phns": "aa nf_nn yv ng_h0 aa_s0 ee_yo",
            "fst": "1v2yfgYAAAB2ZWN0b3IIAAAAc3RhbmRhcmQCAAAAAAAAAAMAQg..."
        }'
        ```

    - Response

        | HTTP error code | description |
        |---|:---:|
        | 200 | OK |
        | 400 | Bad Request |
        | 500 | Internal Server Error |

        body
        ```js
        {
            "id":"1000",        // 전달된 id 값
            "error_code":0,     // error code : 정상시 0
            "result": "speechpro 제공 결과값 json string"
        }
        ```

        body (error 발생의 경우)
        ```js
        {
            "id": "1000",
            "error_code": error code,
            "result": "error message"
        }
       ```

7. wave string(base64)를 통한 발음평가

    /speechpro/gtp<br/>
    /speechpro/model<br/>
    순서대로 수행한 결과를 입력으로 넣어 발음평가 결과를 얻어냅니다.<br/>
    이 방법은 json 내부에 wav 의 내용을 base64로 넣어서 scoring 하는 방법입니다.<br/>

    - Request

        | HTTP endpoint | conent-type | method |
        |---|:---:|:---:|
        | /speechpro/score | application/json | POST |

        ```sh
        curl -X POST -H "Content-Type: application/json" http://<주소>:<포트>/speechpro/score -d '
        {
            "id": "1000",
            "text": "안녕하세요",
            "syll_ltrs": "안_녕_하_세_요",
            "syll_phns": "aa nf_nn yv ng_h0 aa_s0 ee_yo",
            "fst": "1v2yfgYAAAB2ZWN0b3IIAAAAc3RhbmRhcm...",
            "wav_usr": "UklGRno2AQBXQVZFZm10IBAA..."
        }'
        ```

    - Response

        | HTTP error code | description |
        |---|:---:|
        | 200 | OK |
        | 400 | Bad Request |
        | 500 | Internal Server Error |

        body
        ```js
        {
            "id":"1000",        // 전달된 id 값
            "error_code":0,     // error code : 정상시 0
            "result": "speechpro 제공 결과값 json string"
        }
        ```

        body (error 발생의 경우)
        ```js
        {
            "id": "1000",
            "error_code": error code,
            "result": "error message"
        }
        ```

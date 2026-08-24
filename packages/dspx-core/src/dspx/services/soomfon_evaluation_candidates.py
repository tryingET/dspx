"""Frozen Soomfon candidate, input, and receipt identities."""

from __future__ import annotations

EXPECTED_INPUT_SHA256 = {
    "simple": "504ff94159b06c326d71068ed325aeefc52459d6c7ae956d75c1b261c86a6900",
    "elaborate": "ed18493c4c17b8a36a30c8d309773845326cb5e4d85edeffad14b052d53e7a16",
    "researched": "99c4c8a9fc5b002e5a1167f97213cfb04c36590d55c95825417a4e19ba943812",
    "deep-research": "f71f02df9921fc502700ec8ab1d102b0092b2870b52ee583a440a95ddc08d01b",
    "socratic": "4693caea691634f9d63cd1e519038baf0a2663b876e110cb06ee0f07af7c6686",
    "bloom": "53e937b087ce752f8ead60dec3151aabda3fee3c76e99cc31a28081c4683c829",
}
EXPECTED_RECEIPT_SHA256 = {
    "simple": "0e193d10d1a9c7f1e6e7642a560c877e95297de60c7a27bd056317a8ee8efb7b",
    "elaborate": "662cc899182f6723425eb0a02e675482a09e13c810a0c877a706a54fc90e603b",
    "researched": "9abd66aceb67113a8d4453d403a720c1b0de28e296aeb586bdea472ea5161cc1",
    "deep-research": "f55bfaf9666c07dafe46a626f212eb5712f456835f2f3494806ad104c575a462",
    "socratic": "e7ea97c23a799bccba09aded84064253b628323d68f8fb9c7df2760d18e4d917",
    "bloom": "56afe306bd14d64bcf722d502acda3719f6fd46c90e8cce673443250bf97c8cf",
}
PROTECTED_MANIFESTS = {
    "aa0b473e7f0cd056246149eacfcb25c5ed023ab61a1b9410103443e68c30fac1": "simple",
    "1304cc07864c241ab9b66e19589394e729640204996b317c0286c628d8e727cd": "elaborate",
    "bc3fbd7dc5d4993d93ee1af9737be7d12720d67a4df7793509e171e094cfe051": "researched",
    "03e4d23e6d0eede3cd474d5d84d8fc1091e3c52c3b5c318f4b9be686e71c09fa": "deep-research",
    "01b28caa003943e616ad07815870f1abb0f200d0990e52f487271c79ed855fac": "socratic",
    "087994808d60ee46b7283c4d8f0b7c269323c016c392d1e9bdee075abe8a53ba": "bloom",
    "ed0fd9db0268aef35fa5cd7314800b26a66864afd384271785fb0a09b5b24cd4": "simple",
    "7025d592f61b3afe70440ca3f3420736998cd286ed47761596f3e9458538f699": "elaborate",
    "69696b0d12cb0694b0a63ea3270bb7503df2a70f9112e51a5a152307f104aa5c": "researched",
    "8aebeda59ab883211c5318208f53086febc802e195170442cf6c0bc4c62fab5c": "deep-research",
    "ce43ee0674fd1adc1141f929d12cc897f8537bbd8be15475110e62d5d2810f95": "socratic",
    "77dc9cf7bf265f719160e4eea6547801255ad745b92b886a46b8cc0c672f39a0": "bloom",
}

from app.services.memory_service import MemoryService


# ========================================================
# NAME
# ========================================================

def test_extract_name():
    assert (
        MemoryService._extract_name("My name is Ahmed.")
        == "Ahmed"
    )


def test_extract_name_with_ime():
    assert (
        MemoryService._extract_name("I'm Ahmed.")
        == "Ahmed"
    )


def test_name_does_not_confuse_profession():
    assert (
        MemoryService._extract_name("I'm a designer.")
        is None
    )


def test_invalid_name_is_rejected():
    assert (
        MemoryService._validate_name("!!!")
        is False
    )


# ========================================================
# STUDY
# ========================================================

def test_extract_study():
    assert (
        MemoryService._extract_study(
            "I study Computer Science."
        )
        == "Computer Science"
    )


def test_extract_study_with_studying():
    assert (
        MemoryService._extract_study(
            "I'm studying   Physics!!!"
        )
        == "Physics"
    )


def test_extract_study_with_major():
    assert (
        MemoryService._extract_study(
            "My major is Mathematics!!!"
        )
        == "Mathematics"
    )


def test_extract_student_sentence():
    assert (
        MemoryService._extract_study(
            "I'm a Computer Science student."
        )
        == "Computer Science"
    )


# ========================================================
# LOCATION
# ========================================================

def test_extract_location():
    assert (
        MemoryService._extract_location(
            "I live in Algeria."
        )
        == "Algeria"
    )


# ========================================================
# LANGUAGE
# ========================================================

def test_extract_language():
    assert (
        MemoryService._extract_language(
            "I speak Arabic."
        )
        == "Arabic"
    )


# ========================================================
# PROFESSION
# ========================================================

def test_extract_job():
    assert (
        MemoryService._extract_job(
            "I'm a designer."
        )
        == "designer"
    )


def test_extract_job_without_article():
    assert (
        MemoryService._extract_job(
            "I work as developer."
        )
        == "developer"
    )


# ========================================================
# AGE
# ========================================================

def test_extract_age():
    assert (
        MemoryService._extract_age(
            "I am 18 years old."
        )
        == "18"
    )


def test_extract_short_age():
    assert (
        MemoryService._extract_age(
            "I'm 19."
        )
        == "19"
    )


def test_invalid_age():
    assert (
        MemoryService._validate_age("999")
        is False
    )


def test_valid_age():
    assert (
        MemoryService._validate_age("18")
        is True
    )


# ========================================================
# NORMALIZATION
# ========================================================

def test_normalize_value():
    assert (
        MemoryService._normalize_value(
            "   Physics!!!   "
        )
        == "Physics"
    )


def test_empty_normalized_value():
    assert (
        MemoryService._normalize_value(
            "!!!"
        )
        is None
    )


# ========================================================
# GENERIC TEXT VALIDATION
# ========================================================

def test_valid_text():
    assert (
        MemoryService._validate_text(
            "Computer Science"
        )
        is True
    )


def test_invalid_text():
    assert (
        MemoryService._validate_text(
            "!!!"
        )
        is False
    )
def test_extract_name_from_natural_sentence():
    content = "Hi, my name is Ahmed, nice to meet you."

    assert MemoryService._extract_name(content) == "Ahmed"


def test_extract_study_from_natural_sentence():
    content = "Just so you know, I study Computer Science at university."

    assert MemoryService._extract_study(content) == "Computer Science"


def test_extract_location_from_natural_sentence():
    content = "I currently live in Algeria, near my university."

    assert MemoryService._extract_location(content) == "Algeria"

def test_extract_name_does_not_confuse_profession():
    content = "I'm a designer."

    assert MemoryService._extract_name(content) is None


def test_extract_job_from_natural_sentence():
    content = "I work as a designer at a local company."

    assert MemoryService._extract_job(content) == "designer"


def test_extract_job_from_combined_sentence():
    content = "I'm a designer and I study Computer Science."

    assert MemoryService._extract_job(content) == "designer"
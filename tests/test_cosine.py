"""코사인 유사도·랭킹 단위 테스트 (순수, 네트워크/DB 0)."""

import pytest

from app.scoring.cosine import cosine_similarity, rank_by_cosine


def test_identical_vectors_is_one():
    assert cosine_similarity([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]) == pytest.approx(1.0)


def test_orthogonal_is_zero():
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)


def test_opposite_is_negative():
    assert cosine_similarity([1.0, 0.0], [-1.0, 0.0]) == pytest.approx(-1.0)


def test_zero_vector_is_zero():
    assert cosine_similarity([0.0, 0.0], [1.0, 1.0]) == 0.0


def test_dimension_mismatch_raises():
    with pytest.raises(ValueError):
        cosine_similarity([1.0], [1.0, 2.0])


def test_rank_orders_by_similarity_desc_and_top_n():
    query = [1.0, 0.0]
    candidates = [
        (1, [0.0, 1.0]),  # 직교 → 0
        (2, [1.0, 0.0]),  # 동일 → 1
        (3, [1.0, 1.0]),  # 45도 → ~0.707
    ]
    ranked = rank_by_cosine(query, candidates, top_n=2)
    assert [cid for cid, _ in ranked] == [2, 3]
    assert ranked[0][1] == pytest.approx(1.0)

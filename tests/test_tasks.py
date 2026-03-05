from app.tasks import export_task, fetch_task, rescore_task, score_task


class TestTaskWrappersExist:
    def test_fetch_task_is_callable(self):
        assert callable(fetch_task)

    def test_score_task_is_callable(self):
        assert callable(score_task)

    def test_rescore_task_is_callable(self):
        assert callable(rescore_task)

    def test_export_task_is_callable(self):
        assert callable(export_task)

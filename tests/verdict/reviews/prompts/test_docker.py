from verdict.reviews.prompts import find_docker_files


def test_finding_the_students_docker_files():
    paths = ["Makefile", "Dockerfile", "srcs/requirements/nginx/Dockerfile", "srcs/docker-compose.yml", "compose.yaml", "docker-compose.override.yml",
             "app.dockerfile", "Dockerfile.dev", "notes/dockerfile.txt", "mlx/Dockerfile", "a/b/c/d/e/Dockerfile", "node_modules/x/Dockerfile", "docker-compose.md"]
    assert find_docker_files(paths) == ["Dockerfile", "Dockerfile.dev", "app.dockerfile", "compose.yaml", "docker-compose.override.yml",
                                        "srcs/docker-compose.yml", "srcs/requirements/nginx/Dockerfile"]
    assert find_docker_files(["Makefile", "main.c"]) == []
    assert len(find_docker_files([f"d{n}/Dockerfile" for n in range(40)])) == 12

import os


def export_project_to_txt(output_filename):
    # Расширения файлов, которые нужно прочитать
    valid_extensions = ('.py', '.txt', '.md', '.json', '.yaml', '.yml', '.html', '.css', '.js')
    # Папки, которые нужно пропустить
    exclude_dirs = ('.idea', 'venv', '__pycache__', '.git')

    with open(output_filename, 'w', encoding='utf-8') as outfile:
        for root, dirs, files in os.walk('.'):
            # Пропускаем ненужные директории
            dirs[:] = [d for d in dirs if d not in exclude_dirs]

            for file in files:
                if file.endswith(valid_extensions) and file != output_filename:
                    file_path = os.path.join(root, file)
                    try:
                        with open(file_path, 'r', encoding='utf-8') as infile:
                            outfile.write(f"\n\n{'=' * 20}\n")
                            outfile.write(f"FILE: {file_path}\n")
                            outfile.write(f"{'='*20}\n\n")
                            outfile.write(infile.read())
                    except Exception as e:
                        print(f"Ошибка чтения {file_path}: {e}")


if __name__ == '__main__':
    export_project_to_txt('full_project.txt')
    print("Проект успешно записан в full_project.txt")

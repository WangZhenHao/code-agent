from app.models.llm import get_model






def main():
    llm = get_model('gpt-5.5')
    result = llm.invoke("What is the meaning of life?")

    
    print('111')

    print(result)


if __name__ == "__main__":
    main()
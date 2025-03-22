import re

def generate_report_from_outline(llm_client, transcript_text, outline):
    report_prompt = """
    You are given a transcript where the user has brain dumped their thoughts.
    Your task is to generate an article based on the transcript. You'll be given an outline of the article you will be generating.

    Rules:
    - You are only generating an article based on the transcript, not adding or changing views.
    - Remember to follow the outline you are given. Use the article as a guide to generate a proper article that fully catalogs and organizes the users brain dump.
    - Be faithful in translating the users thoughts and ideas. It is very important to not change/inject views.
    - The outline is to show you the flow of the article. you dont have to write in bullet points with headers.
    - Always follow best practices for writing articles. Use varying sentence structures and paragraphs.
    - Use proper grammar and spelling and punctuation.


    Output format:
    - Output a markdown codeblock with ```markdown\n<article_content>\n```
    - The article will be parsed by grabbing the content between the `````` tags.
    - The article should be wellformatted markdown.
    """

    user_prompt = f"""
    Here is the transcript:
    <transcript>
    {transcript_text}
    </transcript>
    
    Here is the outline of the report you will be generating:
    <outline>
    {outline}
    </outline>
    """

    response = llm_client.chat.completions.create(
        model="google/gemini-2.0-flash-001",
        messages=[
            {"role": "system", "content": report_prompt},
            {"role": "user", "content": user_prompt}
        ]
    )

    report = response.choices[0].message.content
    print(report)
    report_match = re.search(r'```markdown\n(.*?)\n```', report, re.DOTALL)
    if report_match:
        report = report_match.group(1).strip()
    return {"report": report}


def outline_report(llm_client, transcript_text):

    outline_prompt = """
    You are given a transcript where the user has braindumped their thoughts.
    Your job is to identify the main points and come up with a outline for a report.
    How to do this:
    - Identify the topics that the user is talking about
    - Group the topics into sections
    - Think about how the overall article should flow depending on the topics, their relationships, and how much and what is said about them
    - You are only organizing and adding cohesiveness to the users braindump, not adding or changing views.

    Output format:
    - Output a markdown codeblock with ```<outline_content>```
    """

    response = llm_client.chat.completions.create(
        model="google/gemini-2.0-flash-001",
        messages=[
            {"role": "system", "content": outline_prompt},
            {"role": "user", "content": transcript_text}
        ]
    )
    return {"outline": response.choices[0].message.content}

if __name__ == "__main__":
    print("No good")
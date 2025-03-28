import re
import json

def generate_report_from_outline(llm_client, transcript_text, outline, article_style):
    report_prompt = """
    You are given:
    - a transcript where the user has brain dumped their thoughts.
    - user specified content style that you will be following.
    - an outline of the content you will be generating.
    
    Your task is to generate a well organized and cohesive content/article based on the transcript.

    Rules:
    - You are only organizing and structuring the user's thoughts into the requested content style based on the transcript, not adding or changing views.
    - Remember to follow the outline you are given. Use the outline as a guide to generate a proper output that fully catalogs and organizes the users brain dump in the requested content style.
    - Be faithful in translating the users thoughts and ideas. It is very important to not change/inject views.
    - The outline is to show you the flow of the content you will be generating. Use it as a flexible guide to help you create writing that is well structured and organized in the requested content style.
    - Dont blindly follow the outline, use your judgement to help you create writing that is well structured and organized in the requested content style. 
    - The outline will always have heading tags and lists, but your output should not have any heading tags or lists unless the is in line with the requested content style.
    - Always follow best practices for writing. It is very important to follow the user provided content style to generate the final output.


    Output format:
    - Output a markdown codeblock with ```\n<article_content_goes_here>\n```
    - The generated content will be parsed by grabbing the content between the ``` ``` tags.
    """

    user_prompt = f"""
    Here is the transcript:
    <transcript>
    {transcript_text}
    </transcript>

    Here is the requested content style:
    <article_style>
    {article_style}
    </article_style>
    
    Here is the outline of the report you will be generating:
    <outline>
    {outline}
    </outline>
    """

    messages = [
        {"role": "system", "content": report_prompt},
        {"role": "user", "content": user_prompt}
    ]
    response = llm_client.chat.completions.create(
        model="google/gemini-2.0-flash-001",
        messages=messages
    )
    report = response.choices[0].message.content
    
    print(json.dumps(messages, indent=2))
    print("--"*50)
    print(report)
    
    report_match = re.search(r'```\s*(.*?)\s*```', report, re.DOTALL)
    if report_match:
        report = report_match.group(1).strip()
    else:
        print("No report found between ``` tags")
    return {"report": report}


def outline_report(llm_client, transcript_text, article_style):

    outline_prompt = """
    You are given a transcript where the user has braindumped their thoughts. Your job is to identify the main points and come up with a outline for structuring and organizing the users thoughts into the form they want. You will be given the format style that the user has specified for the final article that you will need to use in creating the outline.
    
    How to do this:
    - Identify the topics that the user is talking about
    - Carefully consider what the final content the user wants to generate
    - Group the topics into sections that fits the requested content style
    - Think about how the overall article should flow depending on the topics, their relationships, and how much and what is said about them
    - You are only organizing and adding cohesiveness to the users braindump in the requested content style, not adding or changing views.
    - Use <thinking> tags to talk through the process of analyzing, grouping, and structuring the users thoughts.

    Output format:
    - Output the outline in a codeblock with ```\n<outline_content_goes_here>\n```
    - The outline must always be in well formatted markdown between ``` ``` tags
    - the thinking tags must be outside the ``` ``` tags

    """

    response = llm_client.chat.completions.create(
        model="google/gemini-2.0-flash-001",
        messages=[
            {"role": "system", "content": outline_prompt},
            {"role": "user", "content": f"<transcript>\n{transcript_text}\n</transcript>\n\nRequested content style: {article_style}"}
        ]
    )
    outline = response.choices[0].message.content
    print(outline)
    outline_match = re.search(r'```\s*(.*?)\s*```', outline, re.DOTALL)
    if outline_match:
        outline = outline_match.group(1).strip()
    else:
        print("No outline found between ``` tags")
    return {"outline": outline}

if __name__ == "__main__":
    print("No good")
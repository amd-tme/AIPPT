# Default Section

## Untitled Slide


*Notes:*
- Hi! My name is Matt Elliott, and I’m on the Technical Marketing Engineering in the Data Center GPU BU. Today I’m going to walk through an overview of Git, GitHub and related tools, but this course is specifically for non-coders: writers, editors, contributors and other reviewers that need to participate in the “docs as code” workflow.


## Untitled Slide


*Notes:*
- Before we dive into the details, let's quickly frame what we're going to cover. Our goal today is to demystify Git and GitHub so you can confidently participate in the 'docs as code' workflow. 
- The course is structured to guide non-coders through the "docs as code" workflow, which treats documentation like software source code using powerful tools.
- We begin by defining "docs as code" and its core principles, such as source control and transparency.
- Next, we demystify Git version control concepts, covering essential terms like Repository, Commit, Branch, Merge, and Pull Request.
- We then walk through the practical Docs Workflow Cycle, detailing steps from cloning a repository to submitting a Pull Request.
- Following the workflow, we introduce the two main markup languages: Markdown and reStructuredText, explaining where each is best applied.
- Finally, we look at automation with GitHub Actions, which handles tasks like linting, building, and deployment to maintain quality.


## Untitled Slide

- It means treating documentation with the same rigor and tools as software source code.
•
- Source Control: All files are stored in Git.
•
- Collaboration: Use branches and Pull Requests.
•
- Automation: Build and test docs automatically.
•
- Transparency: Full history of who changed what and when.
- What is "Docs-as-Code"?

*Notes:*
- "So, what exactly is 'Docs-as-Code’? It’s more of a mindset than anything else. It means treating documentation with the same rigor, tools, and processes that software engineers use for their source code.
- This approach is built on four core principles you see here:
- Source Control: This is the foundation. All your files—your documentation—are stored in Git. This gives you a complete, safe, and recoverable history of every change.
- Collaboration: Instead of emailing document attachments, we use the core Git features: branches and Pull Requests. This ensures people aren't overwriting each other's work and provides a formal, auditable review process.
- Automation: This is where we take the boring work out of your hands. We use tools like GitHub Actions to automatically run checks, tests, and builds, ensuring quality and consistency every time a change is proposed.
- Transparency: Because of source control, you get a full history of the document. You always know who changed what, when they changed it, and why."


## Untitled Slide


*Notes:*
- “Let’s look at the first and most powerful principle of 'Docs-as-Code': Source Control.
- Think of Source Control, powered by Git, as a literal time machine for your documentation. Every time you save your changes in this system—what we call making a Commit—you are taking a high-resolution snapshot of your entire project at that exact moment.
- This is the 'time travel' aspect. If you ever make a mistake, or if a change you made three months ago needs to be undone, you are never locked in. You can rewind your document to any point in its history, restoring a clean, working version with a few simple commands. It provides the ultimate safety net and traceability. You can always see who made what change and when, giving you full accountability and a complete, recoverable history."


## Untitled Slide


*Notes:*
- Now, let's talk about GitHub. If Git is the time machine for your content, GitHub is the shared workshop where everyone collaborates. It’s the platform that hosts the repositories and puts a friendly web interface on top of Git. The real power here is collaboration. GitHub gives us tools like Issues to track what needs to be done, and most importantly, Pull Requests. The Pull Request is the heart of the 'docs as code' workflow—it’s where you request to merge your changes, and where your teammates can review, comment, and approve your work before it goes live.
- The final piece of the GitHub puzzle is integration, and this is where you gain the next level of power. We use a feature called GitHub Actions, which acts as your robotic assistant. This tool runs automatically every time you propose a change. It takes the tedious work off your plate by handling essential quality checks like linting and building your raw files into finished HTML. Crucially, it also manages the deployment step. Once all the checks pass, GitHub can automatically publish your new, approved documentation to your final hosting platform, like ReadTheDocs. This automation ensures consistent quality and makes the process of publishing faster and much more reliable.


## Untitled Slide


*Notes:*
- Let’s take a final look at the three critical tasks that automation handles for you, ensuring a consistent, high-quality documentation every time.
- First, Linting is your automated quality control—it catches all the typos, broken links, and style guide issues instantly, before a human ever sees them.
- Second, Building takes your raw Markdown or reStructuredText files and compiles them into a clean, ready-to-publish website, often using a tool like Sphinx. This is how the documentation is formatted for its final audience.
- Finally, Deployment is the last mile. Once all checks pass, your approved, built documentation is automatically published to your final hosting platform, such as Read The Docs. By automating these steps, we remove manual errors and drastically speed up the time from finishing your edit to seeing it live.


## Untitled Slide


*Notes:*
- Before we move on to the actual workflow, I want to briefly address a point of potential confusion: the difference between public GitHub and GitHub Enterprise.
- We use both platforms internally, but they serve different purposes. The key difference is simple: all of our public documentation and the files you will be working with are stored exclusively on public GitHub.
- GitHub Enterprise is typically for internal, private code projects. To avoid any confusion, and to ensure you are working in the correct repository with the correct tools, always make sure you are logged into and accessing the public GitHub instance when working with the documentation files.


## Untitled Slide


*Notes:*
- Now, let's briefly talk about SSH keys. This is a small, one-time setup that acts as a secure, digital key to let you log in to GitHub without typing your password over and over.
- Think of it as a special, private handshake between your computer and GitHub. You generate a pair of keys—a public one you give to GitHub, and a private one that stays on your machine. When you interact with a repository, these keys prove you are who you say you are, making the whole process much faster and more secure.
- In the upcoming hands-on section, we will walk through the exact steps to generate and set up your SSH key, but for now, just know it’s the secure, modern way to connect to your Git repositories.


## Generating an SSH Key

- Open PowerShell
- Press Start → PowerShell to launch it.
- Check for existing SSH keys (optional)
- ls ~/.ssh
- Generate a new SSH key
- ssh-keygen -t ed25519 -C "your_email@amd.com"
- Press Enter to accept the default location
- Enter a passphrase or leave blank


## Initial Git Setup

- Set your identity (required for commits)
- git config --global user.name "Your Name“
- git config --global user.email "your_email@example.com"
- Configure Git SSH authentication
- git config --global core.sshCommand "ssh -i $env:USERPROFILE\.ssh\id_ed25519.pub"
- View your public key
- Located at: %USERPROFILE%\.ssh\id_ed25519.pub
- Open it with:notepad $env:USERPROFILE\.ssh\id_ed25519.pub
- Add your key to GitHub
- Paste the copied .pub key into GitHub → Settings → SSH and GPG keys


## Untitled Slide



## Untitled Slide

- Repository (Repo): The project folder containing all your files and the entire history of changes.
- Commit: A snapshot of your changes at a specific point in time. Think of it as "Save As...".
- Branch: A parallel version of the repo where you can work safely without affecting the main project.
- Merge: The process of combining changes from one branch into another (e.g., your edits into the main doc).
- Pull Request (PR): A request to merge your changes. This is where review and discussion happen.
- Key Git Concepts

*Notes:*
- We're now diving into the essential vocabulary of Git. 
- First is the Repository, or 'Repo.' This is simply the main project folder that holds all your files, along with the complete history of every change ever made.
- Next, a Commit is your save button. It’s a literal snapshot of all your changes at one specific point in time. 
- A Branch is a parallel version of the project. It lets you work on your content safely without affecting the main, published documentation.
- When your work is done, Merge is the action of combining your changes from your Branch back into the main project.
- Finally, the Pull Request or 'PR' is the request to merge your work. This is the crucial step where you invite your teammates to review, discuss, and approve your changes before they go live.


## Untitled Slide

- GitHub organizes your workflow into visible, manageable units:
•
- Issues: Track bugs, tasks, or feature requests. "We need a new tutorial."
•
- Discussions: Open forums for questions and ideas.
•
- Pull Requests: The heart of collaboration. See exactly what changed, line by line.
- GitHub Collaboration

*Notes:*
- Now, let's look at how GitHub organizes your collaboration and keeps your workflow transparent and manageable.
- First, you have Issues. These can be used tracks bugs, tasks, or feature requests. For documentation, an issue might be something like: 'We need a new tutorial on setting up SSH keys' or 'Fix the broken link on the main page.' It's your to-do list. This is also were we may receive feedback from someone if they find a problem with an existing doc, or want to request a new doc.
- Next are Discussions. These are open forums for general questions, brainstorming ideas, or getting feedback that doesn't necessarily relate to a specific change. Think of it as a community water cooler. We don’t use these heavily now, but they could be a useful tool as we grow.
- Finally, you have Pull Requests, which are the heart of collaboration and the core of the 'docs as code' process. As we discussed, the PR is where you request to merge your changes, but more than that, it provides a dedicated place to see exactly what changed, line by line, making the review and approval process clear and auditable.


## Untitled Slide

2. Clone
- Download the repo to your machine.
3. Branch
- Create a safe space for your edits.
- 4. Edit
- Write content in VS Code.
- 5. Push
- Upload changes to GitHub.
- 6. PR
- Review and Merge.
- The Docs Workflow Cycle
1. Fork
- Create a copy of the repo in your GitHub account

*Notes:*
- So now that we have the vocabulary, let's look at the Docs Workflow Cycle—this is the sequence of steps you will follow every single time you make a documentation change. We'll use the terms we just defined to walk through a simple example.
- First, you might Fork the main repository to create your own personal copy in your GitHub account. This is a common starting point, but not a requirement. I prefer to make a fork of most repos I’m working on, but for simple changes I sometime skip this to save time.
- From there, you Clone the repository, which simply means downloading a copy to your local machine so you can edit the files.
- Next, you Branch. You create a new branch to work in, giving you a safe, parallel workspace where you can make changes without breaking the main documentation.
- Then, you Edit the content. You do your writing and make your changes, perhaps in an editor like VS Code.
- Once your edits are done, you perform a Commit (your save button), followed by a Push, which uploads those committed changes from your local machine up to your branch on GitHub. Once you’re comfortable with the workflow, you may make multiple commits during a work session, then push your commits at the end.
- Finally, you submit a Pull Request, or PR. This is where you ask the team to Merge your branch into the main documentation, and where all the review and discussion happen before your work goes live.


## Untitled Slide

- These 5 commands cover 90% of your work:
- git clone
- git checkout -b
- git add .
- git commit -m
- git push
- Workflow: Command Line

*Notes:*
- Now, while most of your day-to-day work will be simplified by the friendly graphical interface in VS Code, it’s goodto know the underlying command-line fundamentals. The great news is that you don't need to learn hundreds of commands. These five commands you see here will cover about 90% of your work in the 'docs as code' workflow.
- They directly correspond to the cycle we just discussed: you'll use git clone to get the repository, git checkout -b to create your safe, new branch, then git add and git commit to save your changes, and finally git push to upload them to GitHub.
- Mastering these five gives you complete control, and we will be practicing them in our lab session to ensure everyone is comfortable with the Command Line Interface.


## Untitled Slide

- Markdown (.md)
- Simple, readable, and ubiquitous.
- Best for: READMEs, simple docs, comments.
- reStructuredText (.rst)
- Powerful, extensible, and standard for Sphinx.
- Best for: Technical manuals, complex tables, cross-references.
- Lightweight Markup Languages

*Notes:*
- Now lets cover the two main Lightweight Markup Languages you'll encounter: Markdown and reStructuredText.
- "Markdown, which uses the .md file extension, is simple, very readable, and you see it everywhere—it’s ubiquitous. It’s best for quick, simple documents like README files, comments, and basic documentation. You’ll see it used all over GitHub.
- On the other side, you have reStructuredText, which uses the .rst file extension. This is a more powerful and extensible language, and it's the standard for documentation tools like Sphinx. Because of that, it’s may be a better fit for more structured content like technical manuals, complex tables, and cross-referencing between documents.
- So, why do we need to know both? While most documentation repositories will use just one or the other, depending on what the original author set up, you need to be familiar with both. The key is that .rst provides more advanced formatting and extensible options, so you need to know it in case your project requires that.


## Untitled Slide


*Notes:*
- In the 'docs as code' workflow, the reviewer has a critical, active role. It's not just a quick read-through. The main responsibilities are three-fold.
- First, the reviewer can Comment and Suggest edits directly on specific lines of the file. This allows for precise, in-context feedback without having to re-read the entire document.
- Second, they have the power to Request Changes. If the document isn't ready or a key point is missing, the reviewer can formally block the merge until those specific changes are made.
- Finally, they can Approve the Pull Request. This is the official sign-off, confirming that the document meets quality standards and is ready to be merged into the main, published documentation.
- This process ensures quality, consistency, and shared ownership of all our documentation.


## Untitled Slide

- The Pull Request Process
- Pull Requests are not just for merging code; they are for conversation.
•
- Files Changed: View a "diff" of exactly what was added or removed.
•
- Inline Comments: Ask questions or suggest edits on specific lines.
•
- Approvals: Require sign-off from peers before publishing.
- Reviewing & Suggesting

*Notes:*
- Now, let's look closer at the Pull Request process. It's important to remember that a Pull Request is not just a mechanism for merging files; it is fundamentally a space for conversation.
- We achieve this conversation through three main features.
- First, the 'Files Changed' tab is where you get to see the diff—that's the red (deleted) and green (added) highlights that show you exactly what was modified, line by line. This makes spotting the edits instantaneous.
- Second, you can use 'Inline Comments.' This allows you to ask a question or suggest a specific change directly on a single line of a file, which is much more efficient than generic comments.
- And finally, 'Approvals.' This is the formal sign-off. It’s how your teammates confirm that the document meets our quality standards and is officially ready to be merged into the main, published documentation.


## Untitled Slide


*Notes:*
- We'll now zoom in on one of the most powerful features of the Pull Request: Inline Comments and Suggestions. Instead of writing a generic comment at the bottom that says, 'Hey, look at line 42,' GitHub lets you click right next to a line of text in the diff view—that red and green view—and add your comment or suggestion there.
- This is a key part of the workflow. You can not only ask a question about a specific sentence, but you can also use the 'Suggest' feature to propose an exact change to the author. This turns the review into a collaborative editing process rather than just a pass/fail check. The author can then accept your suggestion with a single click, which instantly commits the edit to their branch. This precision speeds up the entire review cycle, keeping the focus exactly where it needs to be.


## Untitled Slide


*Notes:*
- Now, let's look at the Docs Workflow using a tool called Visual Studio Code, or VS Code. This tool is designed to simplify the Git process with a friendly graphical interface, so you don't have to live in the command line.
- It makes a few key parts of the workflow much easier.
- First, the dedicated Source Control Tab acts as your hub—it instantly shows you all the files you've modified and what their status is.
- Next, the Stage and Commit steps are done with simple UI buttons. You can select the files you want to save and write your commit message right within the application.
- The Sync Changes button is incredibly powerful: it handles both the Push to upload your work to GitHub and the Pull to download the latest changes from your team, all with a single click.
- And finally, for our writers, VS Code offers a Live Preview for Markdown. As you type your documentation, you can see exactly how it will render, making the editing process much smoother and faster.


## Untitled Slide


*Notes:*
- Now, let’s talk about a few final concepts that give you complete power over your documentation: Tracking Changes. This is Git's ultimate accountability feature. You can trace the origin of every single line of documentation.
- There are three key ways we do this.
- First, you have the document History. This is simply a timeline that shows you all the commits, letting you see exactly how the document has evolved over time.
- Second, you have Git Blame. This is a powerful feature that lets you point at any line of text and instantly see who last modified it and in which commit. It's incredibly useful for finding context or asking a question to the original author.
- And finally, you have the Diffs. We’ve talked about them, but remember they are the red (deleted) and green (added) highlights that make spotting edits instantaneous in your Pull Request review.
- Together, these features mean you always have a complete, transparent, and recoverable history of your work.


## Untitled Slide

- Docs-as-Code brings the power of software development tools to documentation, enabling better collaboration and quality control.
- Git provides the history and safety net, ensuring no work is ever lost.
- GitHub is your collaboration hub for reviewing changes and managing tasks.
- Automation handles the boring stuff (checking links, building HTML) so you can focus on writing.
- Key Takeaways

*Notes:*
- So, to wrap up, let's cover the Key Takeaways from this course.
- First and foremost, remember that Docs-as-Code brings the power of professional software development tools to our documentation workflow, enabling much better collaboration and quality control.
- Git is your time machine and safety net. It provides the complete history and ensures that no work is ever truly lost.
- GitHub is your shared collaboration hub. It’s where you review changes with Pull Requests, and where you manage tasks with Issues.
- And finally, Automation is your robotic assistant. It handles all the boring stuff—like checking links, building the HTML files, and deployment—so you and your team can focus entirely on writing high-quality content.


## Untitled Slide

- Setup
- Explore
- Read the Sphinx and Markdown documentation to review syntax.
- Lab
- Work through the example repositories listed on the next slide
- Next Steps
- Install git and VS code on your workstation, and create an account on GitHub.com

*Notes:*
- "So, what are your Next Steps? We’ve covered a lot of theory and vocabulary, and now it’s time to put it all into practice. This slide outlines what you should do next to prepare for or continue the hands-on portion of this course.
- For Setup, if you haven't already, please install Git and VS Code on your workstation, and make sure you have an account on GitHub.com. These are the tools we'll be using for the entire lab.
- For Explore, I highly recommend taking some time to review the syntax for Markdown and reStructuredText. A quick read through the official documentation will make your editing process much smoother.
- And finally, for the Lab, your goal is to work through the example repositories listed on the very next slide. These examples are designed to walk you through the core 'Docs Workflow Cycle' using both the command line and VS Code. Let's take a quick look at those repositories now..."


## Workshop Repositories

- https://github.com/AMD-melliott/favorite-restaurants
- https://github.com/AMD-melliott/style-guide-police
- https://github.com/AMD-melliott/global-find-replace
- https://github.com/AMD-melliott/release-notes-compiler
- https://github.com/AMD-melliott/merge-conflict-simulator


## Untitled Slide

- Q&A
- Thank you for joining!
- https://github.com/AMD-melliott
- melliott@amd.com


